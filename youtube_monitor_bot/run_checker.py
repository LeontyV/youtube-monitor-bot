#!/usr/bin/env python3
"""
Periodic checker for YouTube Monitor - run via cron
Uses yt-dlp instead of YouTube API to avoid quota limits.
"""
import os
import sys
from datetime import datetime, timedelta
from dotenv import load_dotenv
import yt_dlp

load_dotenv('/root/.openclaw/workspace/youtube_monitor_bot/.env')

sys.path.insert(0, '/root/.openclaw/workspace/youtube_monitor_bot')

from database import Database
from notifier import TelegramNotifier
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def check_channel_via_ytdlp(channel_id: str, db) -> list:
    """Check channel for new videos using yt-dlp."""
    new_videos = []
    
    try:
        channel_url = f"https://www.youtube.com/channel/{channel_id}/videos"
        
        ydl_opts = {
            'quiet': True,
            'skip_download': True,
            'extract_flat': True,
            'nocheckcertificate': True,
            'socket_timeout': 30,
            'playlistend': 50,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(channel_url, download=False)
            
            if not info or 'entries' not in info:
                return []
            
            entries = list(info.get('entries', [])) or []
            
            for entry in entries[:10]:
                if not entry:
                    continue
                
                video_id = entry.get('id', '')
                if not video_id or db.video_exists(video_id):
                    continue
                
                title = entry.get('title', 'Unknown')
                # Get upload date
                upload_date = entry.get('upload_date', '')
                if upload_date and len(upload_date) == 8:
                    published = f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:]}T00:00:00Z"
                else:
                    published = datetime.now().isoformat() + 'Z'
                
                is_live = 1 if entry.get('was_live', False) else 0
                
                db.add_video(
                    video_id=video_id,
                    channel_id=channel_id,
                    title=title,
                    published_at=published,
                    is_live=is_live
                )
                
                new_videos.append({
                    'video_id': video_id,
                    'title': title,
                    'published_at': published,
                    'is_live': is_live,
                    'channel_id': channel_id
                })
                
    except Exception as e:
        logger.error(f"Error checking channel {channel_id}: {e}")
    
    return new_videos


def main():
    logger.info("Starting YouTube check (yt-dlp)...")
    
    db = Database(os.environ.get('DATABASE_PATH', '/root/.openclaw/workspace/youtube_monitor_bot/data/monitor.db'))
    notifier = TelegramNotifier(
        os.getenv('TELEGRAM_BOT_TOKEN'),
        os.getenv('TELEGRAM_CHAT_ID', '68650276')
    )
    
    channels = db.get_all_channels()
    if not channels:
        logger.info("No channels to check.")
        return
    
    logger.info(f"Checking {len(channels)} channels via yt-dlp...")
    
    all_new = []
    for ch in channels:
        try:
            videos = check_channel_via_ytdlp(ch['channel_id'], db)
            for v in videos:
                v['channel_name'] = ch['name']
                all_new.append(v)
        except Exception as e:
            logger.error(f"Error checking {ch['name']}: {e}")
    
    if all_new:
        logger.info(f"Found {len(all_new)} new videos!")
        notifier.notify_batch(all_new, db)
    else:
        logger.info("No new videos found.")
    
    logger.info("Check complete.")


if __name__ == "__main__":
    main()