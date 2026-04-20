#!/usr/bin/env python3
"""
YouTube API wrapper and channel checking
"""
import os
import httpx
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict

logger = logging.getLogger(__name__)

YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"


class YouTubeChecker:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.client = httpx.Client(timeout=30.0)
    
    def _api_call(self, endpoint: str, params: dict) -> Optional[dict]:
        """Make YouTube API call with error handling."""
        params['key'] = self.api_key
        url = f"{YOUTUBE_API_BASE}/{endpoint}"
        
        try:
            response = self.client.get(url, params=params)
            
            if response.status_code == 200:
                return response.json()
            
            # Parse error
            error_data = response.json() if response.text else {}
            error_msg = error_data.get('error', {}).get('message', response.text)
            error_code = error_data.get('error', {}).get('code', response.status_code)
            
            # Check for specific errors
            if response.status_code == 403:
                errors = error_data.get('error', {}).get('errors', [])
                for err in errors:
                    if err.get('reason') in ['dailyLimitExceeded', 'quotaExceeded']:
                        logger.error("YouTube API quota exceeded!")
                        return {'error': 'quota_exceeded'}
                    if err.get('reason') == 'apiNotActivated':
                        logger.error("YouTube Data API not activated!")
                        return {'error': 'api_not_activated'}
                    if err.get('reason') == 'forbidden':
                        logger.error("API access forbidden - likely blocked")
                        return {'error': 'forbidden'}
            
            if response.status_code == 404:
                logger.error(f"API resource not found: {endpoint}")
                return {'error': 'not_found'}
            
            if response.status_code == 400:
                logger.error(f"Bad API request: {error_msg}")
                return {'error': 'bad_request'}
            
            logger.error(f"API error {response.status_code}: {error_msg}")
            return {'error': 'unknown', 'status': response.status_code, 'message': error_msg}
            
        except httpx.TimeoutException:
            logger.error("YouTube API timeout")
            return {'error': 'timeout'}
        except Exception as e:
            logger.error(f"API call failed: {e}")
            return {'error': 'exception', 'message': str(e)}
    
    def get_channel_info(self, channel_input: str) -> Optional[Dict]:
        """Get channel info by URL, @handle, or ID."""
        # Extract channel ID
        channel_id = self._extract_channel_id(channel_input)
        if not channel_id:
            return None
        
        # Get channel info
        data = self._api_call(
            "channels",
            {
                "part": "snippet,contentDetails",
                "id": channel_id
            }
        )
        
        if not data or 'items' not in data or len(data['items']) == 0:
            return None
        
        item = data['items'][0]
        return {
            'channel_id': item['id'],
            'title': item['snippet']['title'],
            'uploads_playlist': item['contentDetails']['relatedPlaylists']['uploads']
        }
    
    def _extract_channel_id(self, channel_input: str) -> Optional[str]:
        """Extract channel ID from various input formats."""
        # Already an ID
        if channel_input.startswith('UC') and len(channel_input) == 24:
            return channel_input
        
        # @handle
        if channel_input.startswith('@'):
            data = self._api_call(
                "channels",
                {
                    "part": "id",
                    "forHandle": channel_input
                }
            )
            if data and 'items' in data and len(data['items']) > 0:
                return data['items'][0]['id']
            return None
        
        # YouTube URL
        import re
        # https://www.youtube.com/@username
        match = re.search(r'youtube\.com/@(\w+)', channel_input)
        if match:
            return self._extract_channel_id('@' + match.group(1))
        
        # https://www.youtube.com/channel/UCxxxxx
        match = re.search(r'youtube\.com/channel/(UC\w+)', channel_input)
        if match:
            return match.group(1)
        
        # https://www.youtube.com/c/xxxxx
        match = re.search(r'youtube\.com/c/(\w+)', channel_input)
        if match:
            data = self._api_call(
                "channels",
                {"part": "id", "forHandle": '@' + match.group(1)}
            )
            if data and 'items' in data and len(data['items']) > 0:
                return data['items'][0]['id']
        
        return None
    
    def get_upload_playlist(self, channel_id: str) -> Optional[str]:
        """Get uploads playlist ID for channel."""
        data = self._api_call(
            "channels",
            {
                "part": "contentDetails",
                "id": channel_id
            }
        )
        
        if data and 'items' in data and len(data['items']) > 0:
            return data['items'][0]['contentDetails']['relatedPlaylists']['uploads']
        return None
    
    def get_recent_videos(self, playlist_id: str, limit: int = 5) -> List[Dict]:
        """Get recent videos from playlist."""
        data = self._api_call(
            "playlistItems",
            {
                "part": "snippet,contentDetails",
                "playlistId": playlist_id,
                "maxResults": limit
            }
        )
        
        if not data or 'items' not in data:
            return []
        
        videos = []
        for item in data['items']:
            snippet = item['snippet']
            video_id = snippet['resourceId']['videoId']
            published = snippet['publishedAt']
            
            # Check if live
            is_live = snippet.get('liveBroadcastContent') == 'live'
            
            videos.append({
                'video_id': video_id,
                'title': snippet['title'],
                'description': snippet['description'][:200],
                'published_at': published,
                'thumbnail': snippet.get('thumbnails', {}).get('medium', {}).get('url'),
                'is_live': is_live
            })
        
        return videos
    
    def get_video_status(self, video_id: str) -> Optional[Dict]:
        """Get video status (live or not)."""
        data = self._api_call(
            "videos",
            {
                "part": "snippet,liveStreamingDetails",
                "id": video_id
            }
        )
        
        if not data or 'items' not in data or len(data['items']) == 0:
            return None
        
        item = data['items'][0]
        snippet = item['snippet']
        
        result = {
            'title': snippet['title'],
            'is_live': snippet.get('liveBroadcastContent') == 'live',
            'live_viewers': None
        }
        
        if 'liveStreamingDetails' in item:
            result['live_viewers'] = item['liveStreamingDetails'].get('concurrentViewers')
        
        return result
    
    def check_channel(self, channel_id: str, db) -> List[Dict]:
        """Check channel for new videos."""
        uploads_playlist = self.get_upload_playlist(channel_id)
        if not uploads_playlist:
            logger.warning(f"Could not get uploads playlist for {channel_id}")
            return []
        
        # Get recent videos (last 2 to catch any missed)
        videos = self.get_recent_videos(uploads_playlist, limit=3)
        
        new_videos = []
        for video in videos:
            # Check if already in database
            if not db.video_exists(video['video_id']):
                # Add to database
                db.add_video(
                    video_id=video['video_id'],
                    channel_id=channel_id,
                    title=video['title'],
                    published_at=video['published_at'],
                    is_live=video['is_live']
                )
                new_videos.append(video)
                logger.info(f"New video found: {video['title']}")
        
        return new_videos

    def search_videos(self, query: str, days: int = 7, limit: int = 10, region_code: str = None, page_token: str = None) -> dict:
        """Search videos on YouTube by query. Returns dict with videos and nextPageToken."""
        from datetime import datetime, timedelta
        
        # Calculate published_after timestamp
        published_after = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%dT%H:%M:%SZ')
        
        params = {
            "part": "snippet",
            "q": query,
            "type": "video",
            "order": "relevance",
            "publishedAfter": published_after,
            "maxResults": min(limit, 50)
        }
        
        if region_code:
            params["regionCode"] = region_code
        
        if page_token:
            params["pageToken"] = page_token
        
        data = self._api_call("search", params)
        
        if not data or 'items' not in data:
            return {'videos': [], 'next_token': None}
        
        videos = []
        for item in data['items']:
            snippet = item['snippet']
            video_id = item['id']['videoId']
            videos.append({
                'video_id': video_id,
                'title': snippet['title'],
                'description': snippet.get('description', '')[:200],
                'channel_title': snippet.get('channelTitle', 'Unknown'),
                'published_at': snippet['publishedAt'],
                'thumbnail': snippet.get('thumbnails', {}).get('medium', {}).get('url')
            })
        
        return {
            'videos': videos,
            'next_token': data.get('nextPageToken')
        }
