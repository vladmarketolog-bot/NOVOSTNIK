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

import json
import requests

try:
    from googlenewsdecoder import gnewsdecoder
except Exception as e:
    logger.debug(f"googlenewsdecoder library not used: {e}")
    gnewsdecoder = None

def decode_google_news_url_native(source_url: str) -> str:
    """
    Нативно декодирует ссылку Google News через Google batch execute API без внешних сторонних зависимостей.
    """
    try:
        url_obj = urllib.parse.urlparse(source_url)
        path = url_obj.path.split("/")
        if len(path) < 2 or path[-2] not in ["articles", "read"]:
            return source_url
        base64_str = path[-1]

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
        }
        
        # Получаем data-n-a-sg и data-n-a-ts
        r = requests.get(f"https://news.google.com/articles/{base64_str}", headers=headers, timeout=10)
        soup = BeautifulSoup(r.text, "html.parser")
        elem = None
        for div in soup.find_all("div"):
            if div.get("data-n-a-sg"):
                elem = div
                break
        if not elem:
            r = requests.get(f"https://news.google.com/rss/articles/{base64_str}", headers=headers, timeout=10)
            soup = BeautifulSoup(r.text, "html.parser")
            for div in soup.find_all("div"):
                if div.get("data-n-a-sg"):
                    elem = div
                    break
                    
        if not elem or not elem.get("data-n-a-sg"):
            return source_url

        sig = elem.get("data-n-a-sg")
        ts = elem.get("data-n-a-ts")
        payload = [
            "Fbv4je",
            f'["garturlreq",[["X","X",["X","X"],null,null,1,1,"US:en",null,1,null,null,null,null,null,0,1],"X","X",1,[1,1,1],1,1,null,0,0,null,0],"{base64_str}",{ts},"{sig}"]'
        ]
        post_headers = {
            "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
            "User-Agent": headers["User-Agent"]
        }
        resp = requests.post(
            "https://news.google.com/_/DotsSplashUi/data/batchexecute",
            headers=post_headers,
            data=f"f.req={urllib.parse.quote(json.dumps([[payload]]))}",
            timeout=10
        )
        parts = resp.text.split("\n\n")
        if len(parts) > 1:
            parsed = json.loads(parts[1])[:-2]
            decoded_url = json.loads(parsed[0][2])[1]
            return decoded_url
    except Exception as e:
        logger.warning(f"Ошибка при нативном декодировании Google News URL: {e}")
    return source_url

def resolve_url(url: str) -> str:
    """
    Если ссылка ведет на Google News, декодирует её для получения оригинального URL.
    В противном случае переходит по редиректам с помощью HEAD запроса.
    """
    if "news.google.com" not in url:
        return url
    
    # 1. Пробуем нативный надежный декодер
    decoded = decode_google_news_url_native(url)
    if decoded and "news.google.com" not in decoded:
        logger.info(f"Успешно декодирован Google News URL: {decoded}")
        return decoded

    # 2. Пытаемся раскодировать URL через Google News Decoder (если установлен)
    if gnewsdecoder:
        try:
            res = gnewsdecoder(url)
            if res.get("status"):
                decoded_url = res["decoded_url"]
                logger.info(f"Успешно декодирован Google News URL (библиотека): {decoded_url}")
                return decoded_url
        except Exception as e:
            logger.warning(f"Не удалось декодировать Google News URL через библиотеку: {e}")
            
    # Резервный метод с обычным HEAD-запросом
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
            if response.status_code not in (200, 202):
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
