import urllib.parse
import logging
import feedparser
from bs4 import BeautifulSoup
import httpx
import db
import config

# Настройка логирования
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Настройки HTTP-клиента
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}
TIMEOUT = 15.0

def resolve_url(url: str) -> str:
    """
    Некоторые RSS-ленты (например, Google News) используют ссылки-редиректы.
    Функция переходит по редиректам и возвращает конечный URL.
    """
    if "news.google.com" not in url:
        return url
    try:
        with httpx.Client(headers=HEADERS, follow_redirects=True, timeout=TIMEOUT) as client:
            resp = client.head(url)
            return str(resp.url)
    except Exception as e:
        logger.warning(f"Не удалось разрешить редирект для {url}: {e}")
        return url

def fetch_article_text(url: str) -> str:
    """
    Скачивает веб-страницу и извлекает из нее чистый текст статьи.
    Использует эвристику: собирает только параграфы с содержательным текстом.
    """
    try:
        with httpx.Client(headers=HEADERS, follow_redirects=True, timeout=TIMEOUT) as client:
            response = client.get(url)
            if response.status_code != 200:
                logger.warning(f"Ошибка при загрузке статьи {url}: статус {response.status_code}")
                return ""
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Удаляем скрипты, стили, навигацию и подвалы
            for element in soup(["script", "style", "nav", "footer", "header", "aside", "form"]):
                element.decompose()
            
            # Собираем текст из параграфов <p>, которые длиннее 10 слов (чтобы отсечь меню и кнопки)
            paragraphs = soup.find_all('p')
            good_paragraphs = []
            for p in paragraphs:
                p_text = p.get_text().strip()
                if len(p_text.split()) > 10:
                    good_paragraphs.append(p_text)
            
            if not good_paragraphs:
                # Если параграфы не подошли, берем весь текст
                text = soup.get_text(separator="\n")
                lines = [line.strip() for line in text.splitlines() if len(line.strip().split()) > 10]
                return "\n\n".join(lines[:30]) # Ограничиваем первыми 30 строками
            
            return "\n\n".join(good_paragraphs)
    except Exception as e:
        logger.error(f"Ошибка при получении текста статьи {url}: {e}")
        return ""

def get_articles_from_rss(feed_url: str, source_name: str) -> list:
    """
    Парсит RSS-ленту и возвращает список новых статей.
    Использует httpx для обхода блокировок по User-Agent.
    """
    logger.info(f"Парсинг RSS ленты: {feed_url} ({source_name})")
    articles = []
    try:
        with httpx.Client(headers=HEADERS, follow_redirects=True, timeout=TIMEOUT) as client:
            resp = client.get(feed_url)
            if resp.status_code != 200:
                logger.warning(f"Не удалось получить RSS-ленту {feed_url}: статус {resp.status_code}")
                return []
            xml_data = resp.content

        feed = feedparser.parse(xml_data)
        for entry in feed.entries[:10]: # Ограничиваемся последними 10 записями
            url = getattr(entry, 'link', None)
            if not url:
                continue
            
            # Разрешаем редиректы
            resolved_url = resolve_url(url)
            
            # Проверяем, обрабатывали ли её раньше
            if db.is_url_processed(resolved_url):
                continue
                
            title = getattr(entry, 'title', 'No Title')
            published_at = getattr(entry, 'published', '')
            
            articles.append({
                "title": title,
                "url": resolved_url,
                "source": source_name,
                "published_at": published_at
            })
    except Exception as e:
        logger.error(f"Ошибка при парсинге RSS {feed_url}: {e}")
    return articles


def get_google_news_articles() -> list:
    """
    Использует Google News RSS для поиска новостей по ключевым словам за последние 7 дней.
    """
    articles = []
    for keyword in config.SEARCH_KEYWORDS:
        encoded_keyword = urllib.parse.quote(keyword)
        # Ищем новости за последние 7 дней (when:7d)
        google_rss_url = f"https://news.google.com/rss/search?q={encoded_keyword}+when:7d&hl=en-US&gl=US&ceid=US:en"
        logger.info(f"Поиск в Google News по запросу: '{keyword}'")
        
        feed_articles = get_articles_from_rss(google_rss_url, "Google News Search")
        articles.extend(feed_articles)
    
    # Удаляем дубликаты по URL внутри текущей выборки
    unique_articles = {}
    for a in articles:
        unique_articles[a["url"]] = a
        
    return list(unique_articles.values())

def get_all_new_articles() -> list:
    """
    Собирает новые статьи со всех источников (прямые RSS и поиск Google News).
    """
    all_articles = []
    
    # 1. Собираем статьи со стандартных RSS
    for feed_url in config.RSS_FEEDS:
        domain = urllib.parse.urlparse(feed_url).netloc
        all_articles.extend(get_articles_from_rss(feed_url, domain))
        
    # 2. Собираем статьи из Google News по ключевым словам
    all_articles.extend(get_google_news_articles())
    
    # Очистка дубликатов по URL
    unique_articles = {}
    for a in all_articles:
        unique_articles[a["url"]] = a
        
    logger.info(f"Всего найдено {len(unique_articles)} новых (необработанных) статей.")
    return list(unique_articles.values())

# Тестирование модуля
if __name__ == "__main__":
    print("Запуск тестового сбора новостей...")
    # Возьмем одну тестовую ленту
    test_feed = config.RSS_FEEDS[0]
    articles = get_articles_from_rss(test_feed, "Test RSS")
    print(f"Найдено новых статей в тест-ленте: {len(articles)}")
    if articles:
        first = articles[0]
        print(f"Статья: {first['title']}")
        print(f"Ссылка: {first['url']}")
        print("Скачивание содержимого статьи...")
        text = fetch_article_text(first['url'])
        print(f"Длина текста: {len(text)} символов.")
        print(text[:500] + "...")
