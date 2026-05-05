#!/usr/bin/env python3
"""
Telegram notifier for YouTube Monitor
"""
import os
import httpx
import logging
import time
from typing import List, Dict

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot"


class TelegramNotifier:
    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.client = httpx.Client(timeout=30.0)
    
    def _send_message(self, text: str, parse_mode: str = 'Markdown') -> bool:
        """Send message to Telegram."""
        url = f"{TELEGRAM_API}{self.bot_token}/sendMessage"
        
        try:
            response = self.client.post(
                url,
                json={
                    'chat_id': self.chat_id,
                    'text': text,
                    'parse_mode': parse_mode
                }
            )
            
            if response.status_code == 200:
                logger.info(f"Notification sent: {text[:50]}...")
                return True
            else:
                logger.error(f"Failed to send: {response.text}")
                return False
        except Exception as e:
            logger.error(f"Error sending notification: {e}")
            return False
    
    def _send_photo(self, photo_url: str, caption: str, parse_mode: str = 'Markdown') -> bool:
        """Send photo with caption to Telegram."""
        url = f"{TELEGRAM_API}{self.bot_token}/sendPhoto"
        try:
            response = self.client.post(
                url,
                json={
                    'chat_id': self.chat_id,
                    'photo': photo_url,
                    'caption': caption,
                    'parse_mode': parse_mode
                }
            )
            if response.status_code == 200:
                return True
            else:
                logger.warning(f"sendPhoto failed: {response.text}, falling back to text")
                return False
        except Exception as e:
            logger.warning(f"sendPhoto error: {e}, falling back to text")
            return False
    
    def notify_new_video(self, video: Dict, channel_name: str):
        """Notify about new video."""
        video_url = f"https://www.youtube.com/watch?v={video['video_id']}"
        thumbnail = video.get('thumbnail')
        
        emoji = "🔴" if video.get('is_live') else "🆕"
        
        text = (
            f"{emoji} *Новое видео!*\n\n"
            f"📺 *{channel_name}*\n"
            f"🎬 {video['title']}\n\n"
            f"▶️ {video_url}"
        )
        
        if thumbnail and self._send_photo(thumbnail, text):
            return
        self._send_message(text)
    
    def notify_live(self, video: Dict, channel_name: str):
        """Notify about live stream."""
        video_url = f"https://www.youtube.com/watch?v={video['video_id']}"
        viewers = video.get('live_viewers')
        thumbnail = video.get('thumbnail')
        viewers_text = f"👁 {viewers} зрителей" if viewers else ""
        
        text = (
            f"🔴 *СТРИМ!* 🔴\n\n"
            f"📺 *{channel_name}*\n"
            f"🎬 {video['title']}\n"
            f"{viewers_text}\n\n"
            f"▶️ {video_url}"
        )
        
        if thumbnail and self._send_photo(thumbnail, text):
            return
        self._send_message(text)
    
    def notify_batch(self, videos: List[Dict], db):
        """Notify about batch of videos."""
        if not videos:
            return
        
        for video in videos:
            try:
                if video.get('is_live'):
                    self.notify_live(video, video['channel_name'])
                else:
                    self.notify_new_video(video, video['channel_name'])
                
                # Mark as notified
                db.mark_notified(video['video_id'])
                
                # Small delay to avoid rate limits
                time.sleep(0.5)
                
            except Exception as e:
                logger.error(f"Error notifying video {video['video_id']}: {e}")
    
    def close(self):
        """Close httpx client."""
        self.client.close()
    
    def send_status(self, channels_count: int, recent_count: int):
        """Send status update."""
        text = (
            f"📊 *YouTube Monitor*\n\n"
            f"📺 Каналов: {channels_count}\n"
            f"🎬 Видео в базе: {recent_count}\n"
            f"✅ Мониторинг активен!"
        )
        
        self._send_message(text)
