#!/usr/bin/env python3
"""
YouTube checker using yt-dlp (no API key required)
"""
import os
import re
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict

logger = logging.getLogger(__name__)

import yt_dlp


class YouTubeChecker:
    def __init__(self, api_key: str = None):
        """API key is ignored - yt-dlp doesn't need it."""
        self.ydl_opts = {
            'quiet': True,
            'skip_download': True,
            'extract_flat': False,
            'nocheckcertificate': True,
            'socket_timeout': 30,
        }
    
    def _extract_channel_id(self, channel_input: str) -> Optional[str]:
        """Extract channel ID/handle from various input formats."""
        # Already a channel ID
        if channel_input.startswith('UC') and len(channel_input) == 24:
            return channel_input
        
        # @handle or full URL with @
        handle = channel_input
        match = re.search(r'youtube\.com/@(\w+)', channel_input)
        if match:
            handle = '@' + match.group(1)
        elif not channel_input.startswith('@'):
            # Try as-is
            pass
        
        if handle.startswith('@'):
            # yt-dlp can extract channel info from @handle
            return handle
        
        # https://www.youtube.com/channel/UCxxxxx
        match = re.search(r'youtube\.com/channel/(UC\w+)', channel_input)
        if match:
            return match.group(1)
        
        # https://www.youtube.com/c/xxxxx
        match = re.search(r'youtube\.com/c/(\w+)', channel_input)
        if match:
            return '@' + match.group(1)
        
        # Plain text - treat as @handle (search by channel name)
        if channel_input.startswith('@'):
            return channel_input
        return '@' + channel_input

    def get_channel_info(self, channel_input: str) -> Optional[Dict]:
        """Get channel info by URL, @handle, or ID using yt-dlp."""
        channel_id = self._extract_channel_id(channel_input)
        if not channel_id:
            return None
        
        url = f"https://www.youtube.com/{channel_id}" if channel_id.startswith('@') else \
              f"https://www.youtube.com/channel/{channel_id}" if channel_id.startswith('UC') else \
              channel_input
        
        try:
            # Use extract_flat=True to get only channel metadata, not videos
            # (avoids age-restricted video errors)
            opts = self.ydl_opts.copy()
            opts['extract_flat'] = True
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
            
            if not info:
                return None
            
            channel_id = info.get('channel_id') or info.get('id')
            title = info.get('channel') or info.get('title', 'Unknown')
            
            # Get uploads playlist - try to extract from channel page
            uploads_playlist = None
            if 'entries' not in info:  # Not a playlist
                # Try to get uploads playlist from channel page
                channel_url = f"https://www.youtube.com/channel/{channel_id}/videos"
                try:
                    with yt_dlp.YoutubeDL(opts) as ydl:
                        videos_info = ydl.extract_info(channel_url, download=False)
                    if videos_info and 'entries' in videos_info:
                        uploads_playlist = channel_id  # Use channel ID as identifier
                except:
                    uploads_playlist = channel_id  # Fallback
            else:
                uploads_playlist = channel_id
            
            return {
                'channel_id': channel_id,
                'title': title,
                'uploads_playlist': uploads_playlist,
                'thumbnail': info.get('thumbnail'),
                'subscribers': info.get('subscriber_count'),
            }
        except Exception as e:
            logger.error(f"Error getting channel info for {channel_input}: {e}")
            return None
    
    def get_video_upload_date(self, video_id: str) -> Optional[str]:
        """Get upload date for a single video. Fast, uses extract_flat=True."""
        url = f"https://www.youtube.com/watch?v={video_id}"
        try:
            opts = self.ydl_opts.copy()
            opts['extract_flat'] = True
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
            return info.get('upload_date') if info else None
        except Exception as e:
            logger.error(f"Error getting upload date for {video_id}: {e}")
            return None

    def get_recent_videos(self, channel_id: str, limit: int = 5) -> List[Dict]:
        """Get recent videos from channel using yt-dlp."""
        # Build URL
        if channel_id.startswith('@'):
            url = f"https://www.youtube.com/{channel_id}/videos"
        elif channel_id.startswith('UC'):
            url = f"https://www.youtube.com/channel/{channel_id}/videos"
        else:
            url = f"https://www.youtube.com/{channel_id}/videos"
        
        try:
            opts = self.ydl_opts.copy()
            opts['extract_flat'] = 'in_playlist'
            opts['ignoreerrors'] = True
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
            
            if not info or 'entries' not in info:
                return []
            
            videos = []
            for entry in list(info['entries'])[:limit]:
                if not entry:
                    continue
                
                video_id = entry.get('id') or entry.get('video_id')
                if not video_id:
                    continue
                
                # Check if live
                is_live = entry.get('live_status') == 'is_live' or \
                         entry.get('was_live') == True or \
                         'live' in entry.get('title', '').lower()
                
                videos.append({
                    'video_id': video_id,
                    'title': entry.get('title', 'Unknown'),
                    'description': entry.get('description', '')[:200],
                    'published_at': entry.get('upload_date') or entry.get('published_at'),
                    'thumbnail': entry.get('thumbnail'),
                    'is_live': is_live,
                    'url': f"https://www.youtube.com/watch?v={video_id}",
                })
            
            return videos
        except Exception as e:
            logger.error(f"Error getting recent videos: {e}")
            return []

    def get_live_streams(self, channel_id: str) -> List[Dict]:
        """Get currently live streams from channel."""
        # Try to get live stream directly
        if channel_id.startswith('@'):
            url = f"https://www.youtube.com/{channel_id}"
        elif channel_id.startswith('UC'):
            url = f"https://www.youtube.com/channel/{channel_id}"
        else:
            url = f"https://www.youtube.com/{channel_id}"
        
        try:
            opts = self.ydl_opts.copy()
            opts['extract_flat'] = 'in_playlist'
            opts['ignoreerrors'] = True
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
            
            if not info:
                return []
            
            # Check if channel/video is currently live
            entries = info.get('entries', [info]) if 'entries' in info else [info]
            
            live_videos = []
            for entry in entries:
                if not entry:
                    continue
                
                is_live = entry.get('live_status') == 'is_live' or \
                         entry.get('is_upcoming') == True
                
                if is_live:
                    video_id = entry.get('id') or entry.get('video_id')
                    live_videos.append({
                        'video_id': video_id,
                        'title': entry.get('title', 'Unknown'),
                        'description': entry.get('description', '')[:200],
                        'published_at': entry.get('upload_date') or entry.get('published_at'),
                        'thumbnail': entry.get('thumbnail'),
                        'is_live': True,
                        'url': f"https://www.youtube.com/watch?v={video_id}" if video_id else None,
                    })
            
            return live_videos
        except Exception as e:
            logger.error(f"Error getting live streams: {e}")
            return []

    def get_video_status(self, video_id: str) -> Optional[Dict]:
        """Get video status (live or not)."""
        url = f"https://www.youtube.com/watch?v={video_id}"
        
        try:
            with yt_dlp.YoutubeDL(self.ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
            
            if not info:
                return None
            
            return {
                'title': info.get('title', 'Unknown'),
                'is_live': info.get('live_status') == 'is_live',
                'live_viewers': info.get('concurrent_viewer_count'),
            }
        except Exception as e:
            logger.error(f"Error getting video status: {e}")
            return None

    def check_channel(self, channel_id: str, db) -> List[Dict]:
        """Check channel for new videos and live streams."""
        new_videos = []
        
        # Check for live streams first
        live_streams = self.get_live_streams(channel_id)
        for video in live_streams:
            if not db.video_exists(video['video_id']):
                # Fetch date if missing
                pub_at = video.get('published_at')
                if not pub_at:
                    pub_at = self.get_video_upload_date(video['video_id'])
                db.add_video(
                    video_id=video['video_id'],
                    channel_id=channel_id,
                    title=video['title'],
                    published_at=pub_at,
                    is_live=1
                )
                video['published_at'] = pub_at
                new_videos.append(video)
                logger.info(f"LIVE stream found: {video['title']}")
        
        # Get recent videos (last 5 to catch any missed)
        videos = self.get_recent_videos(channel_id, limit=5)
        
        for video in videos:
            # Skip if already marked as live
            if video.get('is_live'):
                continue
            # Check if already in database
            if not db.video_exists(video['video_id']):
                # Fetch date if missing
                pub_at = video.get('published_at')
                if not pub_at:
                    pub_at = self.get_video_upload_date(video['video_id'])
                db.add_video(
                    video_id=video['video_id'],
                    channel_id=channel_id,
                    title=video['title'],
                    published_at=pub_at,
                    is_live=0
                )
                video['published_at'] = pub_at
                new_videos.append(video)
                logger.info(f"New video found: {video['title']}")
        
        return new_videos

    def search_videos(self, query: str, days: int = 7, limit: int = 10, region_code: str = None, page_token: str = None) -> dict:
        """Search videos using yt-dlp (no API quota issues)."""
        search_query = f"ytsearch{limit}:{query}"
        
        if region_code:
            search_query = f"ytsearch{limit}:{query} {region_code}"
        
        try:
            opts = self.ydl_opts.copy()
            opts['playlistend'] = limit
            
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(search_query, download=False)
            
            if not info or 'entries' not in info:
                return {'videos': [], 'next_token': None}
            
            videos = []
            for entry in info['entries']:
                if not entry:
                    continue
                
                video_id = entry.get('id') or entry.get('video_id')
                if not video_id:
                    continue
                
                # Filter by days (yt-dlp doesn't filter by date in search)
                upload_date = entry.get('upload_date')
                if upload_date:
                    try:
                        upload_dt = datetime.strptime(upload_date, '%Y%m%d')
                        days_ago = (datetime.now() - upload_dt).days
                        if days_ago > days:
                            continue
                    except:
                        pass
                
                videos.append({
                    'video_id': video_id,
                    'title': entry.get('title', 'Unknown'),
                    'description': entry.get('description', '')[:200],
                    'channel_title': entry.get('channel', 'Unknown'),
                    'published_at': entry.get('upload_date'),
                    'thumbnail': entry.get('thumbnail'),
                    'url': f"https://www.youtube.com/watch?v={video_id}",
                })
            
            return {
                'videos': videos,
                'next_token': None  # yt-dlp doesn't support pagination
            }
        except Exception as e:
            logger.error(f"Error searching videos: {e}")
            return {'videos': [], 'next_token': None}


def ydl_search(query: str, limit: int = 50):
    """Standalone search function for bot.py"""
    opts = {
        'quiet': True,
        'skip_download': True,
        'extract_flat': True,
        'nocheckcertificate': True,
        'socket_timeout': 30,
        'playlistend': limit,
    }
    
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(f"ytsearch{limit}:{query}", download=False)
        if not info or 'entries' not in info:
            return []
        
        return [
            {
                'video_id': e.get('id', ''),
                'title': e.get('title', 'Unknown'),
                'channel_title': e.get('uploader', 'Unknown'),
                'thumbnail': e.get('thumbnail'),
                'url': f"https://www.youtube.com/watch?v={e.get('id','')}",
            }
            for e in info.get('entries', [])
            if e
        ]
