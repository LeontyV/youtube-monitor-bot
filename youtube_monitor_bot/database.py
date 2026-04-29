#!/usr/bin/env python3
"""
SQLite database for YouTube Monitor
"""
import sqlite3
import os
from datetime import datetime
from typing import List, Dict, Optional


class Database:
    def __init__(self, db_path: str = 'data/monitor.db'):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._init_db()
    
    def _get_connection(self):
        return sqlite3.connect(self.db_path)
    
    def _init_db(self):
        """Initialize database tables."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Channels table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS channels (
                channel_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                uploads_playlist TEXT,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Videos table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS videos (
                video_id TEXT PRIMARY KEY,
                channel_id TEXT NOT NULL,
                title TEXT,
                description TEXT,
                thumbnail TEXT,
                published_at TIMESTAMP,
                is_live BOOLEAN DEFAULT FALSE,
                notified BOOLEAN DEFAULT FALSE,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (channel_id) REFERENCES channels(channel_id)
            )
        """)
        
        # Index for faster queries
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_videos_published 
            ON videos(published_at DESC)
        """)
        
        # Filters table for keyword-based monitoring
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS filters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                keywords TEXT NOT NULL,
                days INTEGER DEFAULT 7,
                active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        conn.commit()
        conn.close()
    
    def add_channel(self, channel_id: str, name: str, uploads_playlist: str = None) -> bool:
        """Add a channel. Returns True if new, False if already exists."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute(
                "INSERT OR IGNORE INTO channels (channel_id, name, uploads_playlist) VALUES (?, ?, ?)",
                (channel_id, name, uploads_playlist)
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()
    
    def remove_channel(self, channel_id: str) -> bool:
        """Remove a channel and its videos."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("DELETE FROM videos WHERE channel_id = ?", (channel_id,))
            cursor.execute("DELETE FROM channels WHERE channel_id = ?", (channel_id,))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()
    
    def get_all_channels(self) -> List[Dict]:
        """Get all monitored channels."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("SELECT channel_id, name, uploads_playlist, added_at FROM channels ORDER BY name")
            rows = cursor.fetchall()
            return [
                {
                    'channel_id': row[0],
                    'name': row[1],
                    'uploads_playlist': row[2],
                    'added_at': row[3]
                }
                for row in rows
            ]
        finally:
            conn.close()
    
    def channel_exists(self, channel_id: str) -> bool:
        """Check if channel is monitored."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("SELECT 1 FROM channels WHERE channel_id = ?", (channel_id,))
            return cursor.fetchone() is not None
        finally:
            conn.close()
    
    def add_video(self, video_id: str, channel_id: str, title: str, 
                  published_at: str, is_live: bool = False,
                  description: str = None, thumbnail: str = None) -> bool:
        """Add a video. Returns True if new, False if already exists."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute(
                """INSERT OR IGNORE INTO videos 
                   (video_id, channel_id, title, description, thumbnail, published_at, is_live) 
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (video_id, channel_id, title, description, thumbnail, published_at, is_live)
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()
    
    def video_exists(self, video_id: str) -> bool:
        """Check if video is already in database."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("SELECT 1 FROM videos WHERE video_id = ?", (video_id,))
            return cursor.fetchone() is not None
        finally:
            conn.close()
    
    def get_recent_videos(self, limit: int = 10) -> List[Dict]:
        """Get recent videos from all channels."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                SELECT v.video_id, v.channel_id, v.title, v.published_at, 
                       v.is_live, v.notified, c.name as channel_name
                FROM videos v
                JOIN channels c ON v.channel_id = c.channel_id
                ORDER BY v.published_at DESC
                LIMIT ?
            """, (limit,))
            
            rows = cursor.fetchall()
            return [
                {
                    'video_id': row[0],
                    'channel_id': row[1],
                    'title': row[2],
                    'published_at': row[3],
                    'is_live': bool(row[4]),
                    'notified': bool(row[5]),
                    'channel_name': row[6]
                }
                for row in rows
            ]
        finally:
            conn.close()
    
    def mark_notified(self, video_id: str):
        """Mark video as notified."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("UPDATE videos SET notified = 1 WHERE video_id = ?", (video_id,))
            conn.commit()
        finally:
            conn.close()
    
    def get_unnotified_videos(self) -> List[Dict]:
        """Get videos that haven't been notified yet."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                SELECT v.video_id, v.channel_id, v.title, v.published_at,
                       v.is_live, v.thumbnail, c.name as channel_name
                FROM videos v
                JOIN channels c ON v.channel_id = c.channel_id
                WHERE v.notified = 0
                ORDER BY v.published_at DESC
            """)
            
            rows = cursor.fetchall()
            return [
                {
                    'video_id': row[0],
                    'channel_id': row[1],
                    'title': row[2],
                    'published_at': row[3],
                    'is_live': bool(row[4]),
                    'thumbnail': row[5],
                    'channel_name': row[6]
                }
                for row in rows
            ]
        finally:
            conn.close()

    def add_filter(self, keywords: str, days: int = 7) -> bool:
        """Add a keyword filter."""
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO filters (keywords, days) VALUES (?, ?)",
                (keywords, days)
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def get_filters(self) -> List[Dict]:
        """Get all active filters."""
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT id, keywords, days, active FROM filters WHERE active = 1")
            rows = cursor.fetchall()
            return [{'id': r[0], 'keywords': r[1], 'days': r[2], 'active': bool(r[3])} for r in rows]
        finally:
            conn.close()

    def remove_filter(self, filter_id: int) -> bool:
        """Remove a filter."""
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("DELETE FROM filters WHERE id = ?", (filter_id,))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def search_videos_by_keywords(self, keywords: List[str], days: int = 7) -> List[Dict]:
        """Search videos matching keywords published within days."""
        from datetime import datetime, timedelta
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            placeholders = ' OR '.join(['title LIKE ?' for _ in keywords])
            params = [f'%{kw}%' for kw in keywords] + [cutoff]
            cursor.execute(f"""
                SELECT v.video_id, v.channel_id, v.title, v.published_at,
                       v.is_live, v.thumbnail, c.name as channel_name
                FROM videos v
                JOIN channels c ON v.channel_id = c.channel_id
                WHERE ({placeholders}) AND v.published_at >= ?
                ORDER BY v.published_at DESC
            """, params)
            rows = cursor.fetchall()
            return [
                {
                    'video_id': row[0],
                    'channel_id': row[1],
                    'title': row[2],
                    'published_at': row[3],
                    'is_live': bool(row[4]),
                    'thumbnail': row[5],
                    'channel_name': row[6]
                }
                for row in rows
            ]
        finally:
            conn.close()
