import json
import logging
from pathlib import Path
from datetime import datetime

# Настройка логирования
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Путь к JSON файлу в корне проекта
BASE_DIR = Path(__file__).resolve().parent
DB_FILE_PATH = BASE_DIR / "processed_articles.json"

def load_db() -> dict:
    """
    Загружает базу данных из JSON файла.
    Если файл отсутствует или поврежден, возвращает пустой словарь.
    """
    if not DB_FILE_PATH.exists():
        return {}
    try:
        with open(DB_FILE_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"Не удалось прочитать JSON базу данных, создаем новую: {e}")
        return {}

def save_db(data: dict):
    """
    Сохраняет базу данных в JSON файл с красивым форматированием.
    """
    try:
        with open(DB_FILE_PATH, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Не удалось сохранить базу данных в JSON: {e}")

def is_url_processed(url: str) -> bool:
    """
    Проверяет, обрабатывалась ли ссылка ранее.
    """
    db_data = load_db()
    return url in db_data

def mark_url_processed(url: str, title: str, source: str, published_at: str, status: str, telegram_message_id: int = None):
    """
    Сохраняет ссылку в JSON базу данных со статусом обработки.
    """
    db_data = load_db()
    db_data[url] = {
        "title": title,
        "source": source,
        "published_at": published_at,
        "processed_at": datetime.now().isoformat(),
        "status": status,
        "telegram_message_id": telegram_message_id
    }
    save_db(db_data)

def delete_old_records(days: int = 60):
    """
    Удаляет записи старше определенного количества дней, чтобы файл не разрастался.
    """
    db_data = load_db()
    now = datetime.now()
    urls_to_delete = []

    for url, info in db_data.items():
        processed_at_str = info.get("processed_at")
        if processed_at_str:
            try:
                processed_at = datetime.fromisoformat(processed_at_str)
                delta = now - processed_at
                if delta.days > days:
                    urls_to_delete.append(url)
            except Exception:
                # Если дата некорректна, не удаляем
                continue
                
    if urls_to_delete:
        logger.info(f"Удаление {len(urls_to_delete)} старых записей из базы данных...")
        for url in urls_to_delete:
            del db_data[url]
        save_db(db_data)

# Создаем пустой файл базы данных при первом запуске, если его нет
if not DB_FILE_PATH.exists():
    save_db({})
