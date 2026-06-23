import sys
import time
import logging
from datetime import datetime
from apscheduler.schedulers.blocking import BlockingScheduler
import config
import db
import scraper
import ai_agent
import bot

# Настройка логирования
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

def run_daily_pipeline():
    """
    Основной пайплайн:
    1. Собирает новости
    2. Скачивает тексты
    3. Отправляет в Gemini для фильтрации и генерации постов
    4. Выбирает ОДИН лучший пост (с наивысшим баллом релевантности)
    5. Публикует его в Telegram
    6. Помечает все обработанные статьи в базе данных как завершенные
    """
    logger.info("=== Запуск цикла обработки новостей ===")
    
    try:
        config.validate_config()
    except ValueError as e:
        logger.error(f"Не удалось запустить пайплайн: {e}")
        return

    # Очищаем старые записи из БД (старше 60 дней), чтобы держать её чистой
    try:
        db.delete_old_records(days=60)
    except Exception as e:
        logger.warning(f"Не удалось очистить старые записи БД: {e}")

    # 1. Сбор ссылок на новые статьи
    new_articles = scraper.get_all_new_articles()
    if not new_articles:
        logger.info("Новых новостей в источниках не обнаружено.")
        return

    candidates = []
    
    # 2. Ограничиваем количество анализируемых за раз статей, 
    # чтобы уложиться в лимиты API и времени (максимум 15 статей)
    articles_to_process = new_articles[:15]
    logger.info(f"Начало анализа {len(articles_to_process)} статей с помощью Gemini API...")

    for article in articles_to_process:
        url = article["url"]
        title = article["title"]
        source = article["source"]
        pub_date = article["published_at"]
        
        logger.info(f"Обработка: '{title}' ({source})")
        
        # Скачиваем полный текст статьи
        text = scraper.fetch_article_text(url)
        if not text or len(text.split()) < 100:
            logger.info(f"Статья пропущена (пустой или слишком короткий текст).")
            db.mark_url_processed(url, title, source, pub_date, "ignored")
            continue
            
        # Передаем в ИИ для анализа и генерации текста
        analysis = ai_agent.analyze_and_format_article(title, text, source)
        
        if analysis.get("is_relevant"):
            score = analysis.get("relevance_score", 0)
            logger.info(f"ИИ подтвердил релевантность! Оценка: {score}/100")
            candidates.append({
                "article": article,
                "post_text": analysis.get("post_text"),
                "score": score
            })
        else:
            reason = analysis.get("rejection_reason", "не относится к теме")
            logger.info(f"ИИ отклонил статью. Причина: {reason}")
            # Помечаем как обработанную, чтобы не возвращаться к ней
            db.mark_url_processed(url, title, source, pub_date, "ignored")

    # 3. Публикуем лучшую новость
    if not candidates:
        logger.info("Ни один из материалов не подошел под критерии релевантности ИИ сегодня.")
        return

    # Сортируем по оценке (score) в порядке убывания
    candidates.sort(key=lambda x: x["score"], reverse=True)
    best_candidate = candidates[0]
    
    best_art = best_candidate["article"]
    post_text = best_candidate["post_text"]
    best_score = best_candidate["score"]
    
    logger.info(f"Выбран лучший пост: '{best_art['title']}' с оценкой {best_score}")
    
    # Отправляем в Telegram
    msg_id = bot.post_to_channel(post_text, best_art["url"])
    
    if msg_id:
        db.mark_url_processed(
            best_art["url"], 
            best_art["title"], 
            best_art["source"], 
            best_art["published_at"], 
            "posted", 
            msg_id
        )
        logger.info("Пост успешно опубликован в канале!")
    else:
        logger.error("Сбой публикации поста в Telegram-канал.")

    # 4. Всех остальных кандидатов помечаем в БД как обработанные (пропущенные), 
    # чтобы не предлагать их в следующие дни (так как новость потеряет свежесть)
    for c in candidates[1:]:
        art = c["article"]
        db.mark_url_processed(
            art["url"], 
            art["title"], 
            art["source"], 
            art["published_at"], 
            "ignored"
        )
        
    logger.info("=== Пайплайн завершен ===")

def main():
    logger.info("Бот-редактор запущен!")
    
    # 1. Запуск сбора новостей
    run_daily_pipeline()
    
    # 2. Если запущен с аргументом --loop, настраиваем бесконечный планировщик (для VPS)
    if "--loop" in sys.argv:
        logger.info("Включен режим постоянного планировщика. Настраиваем ежедневный запуск...")
        scheduler = BlockingScheduler()
        
        # Запуск каждый день в 10:00 утра
        scheduler.add_job(
            run_daily_pipeline, 
            'cron', 
            hour=10, 
            minute=0, 
            id='daily_marketing_post'
        )
        
        logger.info("Планировщик настроен. Следующий запуск ежедневно в 10:00.")
        try:
            scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            logger.info("Бот остановлен.")
    else:
        logger.info("Режим однократного запуска. Работа завершена.")

if __name__ == "__main__":
    main()
