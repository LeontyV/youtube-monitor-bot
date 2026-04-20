#!/usr/bin/env python3
"""
Periodic checker for YouTube Monitor - run via cron
Checks all channels and sends notifications

Auto-disables if quota exceeded until next day UTC.
"""
import os
import sys
from datetime import datetime, timedelta
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

QUOTA_FLAG_FILE = '/tmp/youtube_check_disabled'
CRON_FILE = '/etc/cron.d/youtube_monitor_auto'


def is_check_disabled():
    """Check if checking is disabled due to quota exhaustion."""
    if not os.path.exists(QUOTA_FLAG_FILE):
        return False
    
    with open(QUOTA_FLAG_FILE, 'r') as f:
        expiry_str = f.read().strip()
    
    # Parse expiry time (UTC)
    try:
        expiry = datetime.strptime(expiry_str, '%Y-%m-%d %H:%M:%S')
        now = datetime.utcnow()
        
        if now >= expiry:
            # Expired - re-enable checking
            os.remove(QUOTA_FLAG_FILE)
            disable_cron(False)
            logger.info("Quota reset time passed. Re-enabling checks.")
            return False
        else:
            remaining = (expiry - now).total_seconds() // 3600
            logger.info(f"Checks disabled due to quota exhaustion. {remaining:.0f}h until re-enable.")
            return True
    except:
        return False


def disable_checking():
    """Disable checking until next day UTC midnight."""
    now = datetime.utcnow()
    # Next midnight UTC
    next_midnight = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    
    with open(QUOTA_FLAG_FILE, 'w') as f:
        f.write(next_midnight.strftime('%Y-%m-%d %H:%M:%S'))
    
    disable_cron(True)
    logger.info(f"Checks disabled until {next_midnight} UTC")
    
    return next_midnight


def disable_cron(disabled):
    """Enable or disable the cron job."""
    if disabled:
        # Backup and remove cron
        if os.path.exists(CRON_FILE):
            os.rename(CRON_FILE, CRON_FILE + '.disabled')
    else:
        # Re-enable cron
        if os.path.exists(CRON_FILE + '.disabled'):
            os.rename(CRON_FILE + '.disabled', CRON_FILE)


def main():
    logger.info("Starting YouTube check...")
    
    # Check if disabled
    if is_check_disabled():
        logger.info("Checks are disabled. Skipping.")
        return
    
    # Initialize
    db = Database(os.environ.get('DATABASE_PATH', '/root/.openclaw/workspace/youtube_monitor_bot/data/monitor.db'))
    checker = YouTubeChecker(os.getenv('YOUTUBE_API_KEY'))
    notifier = TelegramNotifier(
        os.getenv('TELEGRAM_BOT_TOKEN'),
        os.getenv('TELEGRAM_CHAT_ID', '68650276')
    )
    
    # Get all channels
    channels = db.get_all_channels()
    if not channels:
        logger.info("No channels to check.")
        return
    
    logger.info(f"Checking {len(channels)} channels...")
    
    # Check for API errors first
    test_result = checker._api_call('channels', {'part': 'id', 'id': 'UCWatching'})
    if test_result and isinstance(test_result, dict):
        if 'error' in test_result:
            error_type = test_result.get('error')
            error_msg = f"YouTube API Error: {error_type}"
            
            if error_type == 'quota_exceeded':
                error_msg = "⚠️ YouTube API quota exceeded! Checks disabled until tomorrow UTC."
                logger.error(error_msg)
                notifier._send_message(error_msg)
                expiry = disable_checking()
                notifier._send_message(f"Проверки возобновятся {expiry.strftime('%Y-%m-%d %H:%M UTC')}.")
                return
            
            if error_type == 'forbidden':
                error_msg = "⚠️ YouTube API access forbidden! Possibly banned."
                logger.error(error_msg)
                notifier._send_message(error_msg)
                return
            
            if error_type == 'api_not_activated':
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
