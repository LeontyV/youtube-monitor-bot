# YouTube Monitor Bot

Telegram-бот для мониторинга YouTube каналов и поиска видео.

## Функции

- 🔍 **Поиск видео** — `/search <запрос> <дни>` — поиск видео по ключевым словам
- 📺 **Мониторинг каналов** — `/add_channel <URL>` — добавление канала для отслеживания
- 📋 **Список каналов** — `/list_channels` — просмотр подписок
- 🔄 **Проверка сейчас** — `/check_now` — принудительная проверка новых видео
- ⭐ **Последние видео** — `/recent` — последние видео из подписок

## Установка

```bash
git clone https://github.com/LeontyV/youtube-monitor-bot.git
cd youtube-monitor-bot
pip install -r requirements.txt
cp .env.example .env
# Заполните .env своими токенами
python bot.py
```

## Команды

| Команда | Описание |
|---------|----------|
| `/search <слова> <дни>` | Поиск видео |
| `/add_channel <URL>` | Добавить канал |
| `/list_channels` | Список каналов |
| `/check_now` | Проверить сейчас |
| `/recent` | Последние видео |

## Технологии

- Python 3
- python-telegram-bot
- yt-dlp + YouTube Data API v3
- SQLite

## Лицензия

MIT
