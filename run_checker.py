#!/usr/bin/env python3
"""
Periodic checker for YouTube Monitor - run via cron
Checks all channels and sends notifications
"""
import os
import sys
from dotenv import load_dotenv

# Load .env
load_dotenv('/root/.openclaw/workspace/youtube_monitor_bot/.env')

sys.path.insert(0, '/root/.openclaw/workspace/youtube_monitor_bot')

from checker import YouTubeChecker
from database import Database
from notifier import TelegramNotifier
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    logger.info("Starting YouTube check...")
    
    # Initialize
    db = Database(os.environ.get('DATABASE_PATH', '/root/.openclaw/workspace/youtube_monitor_bot/data/monitor.db'))
    checker = YouTubeChecker(os.getenv('YOUTUBE_API_KEY'))
    notifier = TelegramNotifier(
        os.getenv('TELEGRAM_BOT_TOKEN'),
        os.getenv('TELEGRAM_CHAT_ID', '68650276')
    )
    
    # Get all channels
    channels = db.get_all_channels()
    logger.info(f"Checking {len(channels)} channels...")
    
    # Check for API errors first
    test_result = checker._api_call('channels', {'part': 'id', 'id': 'UCWatching'})
    if test_result and isinstance(test_result, dict):
        if 'error' in test_result:
            error_msg = f"YouTube API Error: {test_result.get('error')}"
            
            if test_result.get('error') == 'quota_exceeded':
                error_msg = "⚠️ YouTube API quota exceeded! Check stopped."
                logger.error(error_msg)
                notifier._send_message(error_msg)
                return
            
            if test_result.get('error') == 'forbidden':
                error_msg = "⚠️ YouTube API access forbidden! Possibly banned."
                logger.error(error_msg)
                notifier._send_message(error_msg)
                return
            
            if test_result.get('error') == 'api_not_activated':
                error_msg = "⚠️ YouTube Data API not activated!"
                logger.error(error_msg)
                notifier._send_message(error_msg)
                return
    
    new_videos = []
    for ch in channels:
        try:
            videos = checker.check_channel(ch['channel_id'], db)
            for v in videos:
                v['channel_name'] = ch['name']
                new_videos.append(v)
        except Exception as e:
            logger.error(f"Error checking {ch['name']}: {e}")
    
    # Send notifications
    if new_videos:
        logger.info(f"Found {len(new_videos)} new videos!")
        notifier.notify_batch(new_videos, db)
    else:
        logger.info("No new videos found.")
    
    logger.info("Check complete.")

if __name__ == "__main__":
    main()
