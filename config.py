import os
from pathlib import Path
from dotenv import load_dotenv

# Находим путь к .env файлу в корне проекта
BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / '.env'

# Загружаем переменные окружения
if ENV_PATH.exists():
    load_dotenv(dotenv_path=ENV_PATH)
else:
    load_dotenv()  # fallback на системные переменные окружения

# Переменные конфигурации
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Настройки ИИ моделей (по умолчанию gemini-3.5-flash)
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")

# Настройки базы данных
DATABASE_PATH = os.getenv("DATABASE_PATH", str(BASE_DIR / "bot_database.db"))

# Настройки скрапера новостей
# Ключевые слова для поиска новостей на английском
SEARCH_KEYWORDS = [
    "marketing LTV",
    "customer retention marketing",
    "retention strategies",
    "growth marketing LTV retention",
    "user retention tips"
]

# RSS источники для мониторинга
RSS_FEEDS = [
    "https://rss.nytimes.com/services/xml/rss/nyt/Technology.xml",
    "https://www.marketingbrew.com/feed",
    "https://feedpress.me/growthhackers",
    "https://neilpatel.com/feed/",
    "https://www.hubspot.com/blog/rss.xml",
    "https://vwo.com/blog/feed/",
]

def validate_config():
    """
    Проверяет наличие обязательных параметров конфигурации.
    """
    missing = []
    if not TELEGRAM_BOT_TOKEN:
        missing.append("TELEGRAM_BOT_TOKEN")
    if not TELEGRAM_CHANNEL_ID:
        missing.append("TELEGRAM_CHANNEL_ID")
    if not GEMINI_API_KEY:
        missing.append("GEMINI_API_KEY")
    
    if missing:
        raise ValueError(
            f"Критическая ошибка конфигурации! Отсутствуют обязательные переменные: {', '.join(missing)}. "
            f"Пожалуйста, создайте файл .env в папке проекта и заполните их."
        )

# Автоматически валидируем при импорте (полезно при запуске)
# Если мы просто импортируем config в тестах, мы можем отключить строгую проверку, 
# но для работы бота она обязательна.
if __name__ == "__main__":
    try:
        validate_config()
        print("Конфигурация успешно загружена и валидна!")
    except ValueError as e:
        print(e)
