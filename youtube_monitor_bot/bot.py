#!/usr/bin/env python3
"""
YouTube Monitor Bot - sends notifications for new videos and streams
"""
import os
import sys
import asyncio
import logging
from datetime import datetime

# Load .env
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

# Initialize yt-dlp with defaults
YDL_OPTS = {
    'quiet': True,
    'skip_download': True,
    'extract_flat': True,
    'nocheckcertificate': True,
    'socket_timeout': 30,
}

def ydl_search(query: str, limit: int = 50):
    """Search YouTube using yt-dlp. Returns list of video dicts."""
    opts = YDL_OPTS.copy()
    opts['playlistend'] = limit
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
        ]

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters, CallbackQueryHandler

# Import modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import yt_dlp
from checker import YouTubeChecker
from database import Database
from notifier import TelegramNotifier

TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
YOUTUBE_API_KEY = os.getenv('YOUTUBE_API_KEY')
ALLOWED_USER_ID = 68650276  # Leonty

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize database
db = Database(os.getenv('DATABASE_PATH', 'data/monitor.db'))


async def auth_check(update: Update) -> bool:
    """Check if user is authorized."""
    return update.effective_user.id == ALLOWED_USER_ID


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await auth_check(update):
        await update.message.reply_text("⛔ Доступ запрещён.")
        return
    
    await update.message.reply_text(
        "📺 YouTube Monitor Bot\n\n"
        "Я слежу за обновлениями на YouTube каналах и уведомляю тебя о новых видео и стримах.\n\n"
        "📋 Команды:\n"
        "/add_channel <URL> — добавить канал\n"
        "/list_channels — список каналов\n"
        "/remove_channel <ID> — удалить канал\n"
        "/check_now — проверить сейчас\n"
        "/status — статус\n"
        "/recent — последние видео со ссылками\n\n"
        "➕ Как добавить:\n"
        "• Ссылка: https://www.youtube.com/@username\n"
        "• Или ID канала: UCxxxxxxxxxxx",
        parse_mode=None
    )


async def add_channel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await auth_check(update):
        await update.message.reply_text("⛔ Доступ запрещён.")
        return
    
    if not context.args:
        await update.message.reply_text("⚠️ Использование: /add_channel <URL или ID канала>")
        return
    
    channel_input = ' '.join(context.args)
    await update.message.reply_text(f"🔍 Ищу канал: {channel_input}...")
    
    checker = YouTubeChecker(YOUTUBE_API_KEY)
    channel_info = checker.get_channel_info(channel_input)
    
    if not channel_info:
        await update.message.reply_text("❌ Канал не найден. Проверь ссылку.")
        return
    
    channel_id = channel_info['channel_id']
    channel_name = channel_info['title']
    
    # Add to database
    success = db.add_channel(channel_id, channel_name)
    
    if success:
        await update.message.reply_text(
            f"✅ *Канал добавлен!*\n\n"
            f"📺 *{channel_name}*\n"
            f"ID: `{channel_id}`\n\n"
            f"Буду уведомлять о новых видео!",
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text(
            f"ℹ️ Канал *{channel_name}* уже в списке.",
            parse_mode='Markdown'
        )


async def list_channels_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await auth_check(update):
        await update.message.reply_text("⛔ Доступ запрещён.")
        return
    
    channels = db.get_all_channels()
    
    if not channels:
        await update.message.reply_text("📭 Список каналов пуст. Добавь первый: /add_channel <URL>")
        return
    
    await update.message.reply_text("📺 Отслеживаемые каналы:", parse_mode='HTML')
    
    for ch in channels:
        channel_url = f"https://www.youtube.com/channel/{ch['channel_id']}"
        text = f"• <a href=\"{channel_url}\">{ch['name']}</a>\n"
        await update.message.reply_text(text, parse_mode='HTML', disable_web_page_preview=True)
        await asyncio.sleep(0.2)


async def remove_channel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await auth_check(update):
        await update.message.reply_text("⛔ Доступ запрещён.")
        return
    
    if not context.args:
        await update.message.reply_text("⚠️ Использование: /remove_channel <ID канала>")
        return
    
    channel_id = ' '.join(context.args)
    
    if db.remove_channel(channel_id):
        await update.message.reply_text("✅ Канал удалён!")
    else:
        await update.message.reply_text("❌ Канал не найден.")


async def check_now_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await auth_check(update):
        await update.message.reply_text("⛔ Доступ запрещён.")
        return
    
    await update.message.reply_text("🔍 Проверяю каналы через yt-dlp...")
    
    channels = db.get_all_channels()
    
    all_new_videos = []
    for ch in channels:
        try:
            channel_url = f"https://www.youtube.com/channel/{ch['channel_id']}/videos"
            
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
                    continue
                
                entries = list(info.get('entries', [])) or []
                
                for entry in entries:
                    if not entry:
                        continue
                    
                    video_id = entry.get('id', '')
                    if not video_id or db.video_exists(video_id):
                        continue
                    
                    title = entry.get('title', 'Unknown')
                    upload_date = entry.get('upload_date', '')
                    if upload_date and len(upload_date) == 8:
                        published = f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:]}T00:00:00Z"
                    else:
                        published = datetime.now().isoformat() + 'Z'
                    
                    is_live = 1 if entry.get('was_live', False) else 0
                    
                    db.add_video(
                        video_id=video_id,
                        channel_id=ch['channel_id'],
                        title=title,
                        published_at=published,
                        is_live=is_live
                    )
                    
                    all_new_videos.append({
                        'video_id': video_id,
                        'title': title,
                        'published_at': published,
                        'is_live': is_live,
                        'channel_name': ch['name']
                    })
                    
        except Exception as e:
            logger.error(f"Error checking {ch['name']}: {e}")
    
    if all_new_videos:
        # Group by channel
        by_channel = {}
        for v in all_new_videos:
            ch_name = v['channel_name']
            if ch_name not in by_channel:
                by_channel[ch_name] = []
            by_channel[ch_name].append(v)
        
        await update.message.reply_text(f"✅ Найдено {len(all_new_videos)} новых видео!")
        await asyncio.sleep(0.3)
        
        for ch_name, videos in by_channel.items():
            text = f"📺 <b>{ch_name}</b> ({len(videos)} новых)\n\n"
            for v in videos[:10]:
                video_url = f"https://www.youtube.com/watch?v={v['video_id']}"
                title = v['title'][:60] + ('...' if len(v['title']) > 60 else '')
                text += f'• <a href="{video_url}">{title}</a>\n'
            
            await update.message.reply_text(text, parse_mode='HTML', disable_web_page_preview=True)
            await asyncio.sleep(0.3)
    else:
        await update.message.reply_text("ℹ️ Новых видео нет.")


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await auth_check(update):
        await update.message.reply_text("⛔ Доступ запрещён.")
        return
    
    channels = db.get_all_channels()
    videos = db.get_recent_videos(limit=5)
    
    text = (
        f"📊 <b>Статус YouTube Monitor</b>\n\n"
        f"📺 Каналов: {len(channels)}\n"
        f"🎬 Видео в базе: {len(videos)}\n\n"
        f"Используй /recent для просмотра видео"
    )
    
    await update.message.reply_text(text, parse_mode=None)



async def recent_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show recent videos with links."""
    if not await auth_check(update):
        await update.message.reply_text("⛔ Доступ запрещён.")
        return
    
    videos = db.get_recent_videos(limit=10)
    
    if not videos:
        await update.message.reply_text("📭 Нет видео в базе.")
        return
    
    channels = {}
    for v in videos:
        ch_name = v.get('channel_name', 'Unknown')
        if ch_name not in channels:
            channels[ch_name] = []
        channels[ch_name].append(v)
    
    await update.message.reply_text("🎬 Последние видео:", parse_mode=None)
    await asyncio.sleep(0.2)
    
    for ch_name, ch_videos in list(channels.items())[:3]:
        text = f"📺 {ch_name}\n"
        for v in ch_videos[:5]:
            video_url = f"https://www.youtube.com/watch?v={v['video_id']}"
            title = v['title'][:50] + ('...' if len(v['title']) > 50 else '')
            text += f'• <a href="{video_url}">{title}</a>\n'
        
        await update.message.reply_text(text, parse_mode='HTML', disable_web_page_preview=True)
        await asyncio.sleep(0.3)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle any text message - provide help."""
    if not await auth_check(update):
        return
    
    await update.message.reply_text(
        "💡 Используй команды:\n"
        "/add_channel — добавить канал\n"
        "/list_channels — список\n"
        "/check_now — проверить сейчас\n"
        "/status — статус\n"
        "/recent — последние видео"
    )


async def filters_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show or add keyword filters."""
    if not await auth_check(update):
        await update.message.reply_text("⛔ Доступ запрещён.")
        return
    
    db = Database(os.path.join(os.path.dirname(__file__), 'data/monitor.db'))
    
    if not context.args:
        filters = db.get_filters()
        if not filters:
            await update.message.reply_text("📭 Фильтры не установлены.\nИспользование: /filters <слова> <дни>")
            return
        
        text = "🔔 Активные фильтры:\n"
        for f in filters:
            text += f"• {f['keywords']} ({f['days']} дн.)\n"
        await update.message.reply_text(text)
        return
    
    args = ' '.join(context.args).split()
    if len(args) < 2:
        await update.message.reply_text("❌ Использование: /filters <слова> <дни>")
        return
    
    try:
        days = int(args[-1])
        keywords = ' '.join(args[:-1])
    except ValueError:
        await update.message.reply_text("❌ Последний аргумент должен быть числом.")
        return
    
    db.add_filter(keywords, days)
    await update.message.reply_text(f"✅ Фильтр добавлен: '{keywords}' ({days} дн.)")





    main()

# Search cache: stores results for pagination
# Search cache with indexed access
search_cache = {}  # cache_id -> {videos, query, days, region}
search_index = 0  # Counter for generating unique IDs

def get_cache_key(query: str, days: int, region: str) -> str:
    return f"{query}|||{days}|||{region or ''}"

async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Search videos by keywords and days."""
    if not await auth_check(update):
        await update.message.reply_text("⛔ Доступ запрещён.")
        return
    
    if not context.args:
        await update.message.reply_text(
            "💡 Использование: /search <слова> <дни> [регион]\n"
            "Пример: /search openclaw 10\n"
            "Пример с регионом: /search python 7 RU"
        )
        return
    
    args = ' '.join(context.args).split()
    if len(args) < 2:
        await update.message.reply_text("❌ Нужны ключевые слова и количество дней.")
        return
    
    region_code = None
    if args[-1].isalpha() and len(args[-1]) == 2:
        region_code = args[-1].upper()
        args = args[:-1]
    
    try:
        days = int(args[-1])
        query = ' '.join(args[:-1])
    except ValueError:
        await update.message.reply_text("❌ Последний аргумент должен быть числом (дни).")
        return
    
    await update.message.reply_text(f"🔍 Ищу '{query}' за {days} дней{', регион ' + region_code if region_code else ''}...")
    
    videos = ydl_search(query, limit=50)
    
    if not videos:
        await update.message.reply_text(f"📭 Ничего не найдено по '{query}' за {days} дн.")
        return
    
    global search_index
    cache_key = get_cache_key(query, days, region_code)
    search_index += 1
    cache_id = search_index
    search_cache[cache_id] = {
        "videos": videos,
        "query": query,
        "days": days,
        "region": region_code
    }
    
    text = f"🔍 Найдено видео по '{query}':\n\n"
    for i, v in enumerate(videos[:10], 1):
        video_url = f"https://www.youtube.com/watch?v={v['video_id']}"
        title = v['title']
        channel = v.get('channel_title', 'Unknown')
        text += f"{i}. <a href=\"{video_url}\">{title}</a>\n   📺 {channel}\n"
    
    keyboard = []
    callback_data = f"search:{cache_id}:10"
    keyboard.append([InlineKeyboardButton("📋 Ещё 10 →", callback_data=callback_data)])
    
    await update.message.reply_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None, disable_web_page_preview=True)


async def search_page_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle pagination for search results."""
    query = update.callback_query
    await query.answer()
    
    if not query.data.startswith('search:'):
        return
    
    try:
        # Format: search:cache_id:offset
        parts = query.data.split(':')
        if len(parts) < 3:
            raise ValueError("Invalid callback data")
        cache_id = int(parts[1])
        offset = int(parts[2])
    except:
        await query.edit_message_text("❌ Ошибка пагинации.")
        return
    
    if cache_id not in search_cache:
        await query.edit_message_text("📭 Кэш поиска устарел. Начните новый поиск.")
        return
    
    cache = search_cache[cache_id]
    videos = cache['videos']
    
    if offset >= len(videos):
        await query.edit_message_text("📭 Конец результатов.")
        return
    
    current_page = offset // 10
    
    text = f"🔍 Результаты '{cache['query']}' ({offset+1}-{min(offset+10, len(videos))} из {len(videos)}):\n\n"
    for i, v in enumerate(videos[offset:offset+10], offset+1):
        video_url = f"https://www.youtube.com/watch?v={v['video_id']}"
        title = v['title']
        channel = v.get('channel_title', 'Unknown')
        text += f"{i}. <a href=\"{video_url}\">{title}</a>\n   📺 {channel}\n"
    
    keyboard = []
    if offset >= 10:
        back_callback = f"search:{cache_id}:{offset - 10}"
        keyboard.append([InlineKeyboardButton("← Назад", callback_data=back_callback)])
    
    new_offset = offset + 10
    if new_offset < len(videos):
        next_callback = f"search:{cache_id}:{min(new_offset, len(videos))}"
        keyboard.append([InlineKeyboardButton("📋 Ещё 10 →", callback_data=next_callback)])
    
    await query.edit_message_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None, disable_web_page_preview=True)

def main():
    logger.info("YouTube Monitor Bot starting...")
    
    app = Application.builder().token(TOKEN).build()
    
    # Commands
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("add_channel", add_channel_command))
    app.add_handler(CommandHandler("list_channels", list_channels_command))
    app.add_handler(CommandHandler("remove_channel", remove_channel_command))
    app.add_handler(CommandHandler("check_now", check_now_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("recent", recent_command))
    app.add_handler(CommandHandler("search", search_command))
    app.add_handler(CommandHandler("filters", filters_command))
    app.add_handler(CallbackQueryHandler(search_page_callback))
    
    # Fallback
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.info("Bot started! Polling...")
    app.run_polling()



if __name__ == "__main__":
    main()
