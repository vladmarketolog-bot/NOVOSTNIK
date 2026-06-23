import logging
import telebot
import config

# Настройка логирования
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Инициализируем бота
if config.TELEGRAM_BOT_TOKEN:
    bot = telebot.TeleBot(config.TELEGRAM_BOT_TOKEN)
else:
    bot = None
    logger.warning("TELEGRAM_BOT_TOKEN не установлен! Бот не сможет отправлять сообщения.")

def format_post(text: str, url: str) -> str:
    """
    Форматирует текст поста для Telegram.
    Заменяет markdown-разметку ИИ (**) на разметку Telegram Markdown (*)
    и подставляет ссылку на первоисточник.
    """
    # Gemini часто выделяет жирный через **, а Telegram Markdown (legacy) требует *
    formatted_text = text.replace("**", "*")
    
    # Формируем красивую ссылку на первоисточник
    source_link = f"\n\n🔗 [Читать первоисточник]({url})"
    
    # Заменяем плейсхолдер {link} на ссылку, либо просто дописываем ссылку в конец
    if "{link}" in formatted_text:
        formatted_text = formatted_text.replace("{link}", source_link)
    elif "{{link}}" in formatted_text:
        formatted_text = formatted_text.replace("{{link}}", source_link)
    else:
        formatted_text += source_link
        
    return formatted_text

def post_to_channel(text: str, url: str) -> int:
    """
    Публикует пост в настроенный Telegram канал.
    Возвращает ID опубликованного сообщения.
    """
    if not bot:
        logger.error("Невозможно отправить сообщение: bot не инициализирован.")
        return None
    
    formatted_text = format_post(text, url)
    
    try:
        logger.info(f"Публикация поста в канал {config.TELEGRAM_CHANNEL_ID}...")
        message = bot.send_message(
            chat_id=config.TELEGRAM_CHANNEL_ID,
            text=formatted_text,
            parse_mode="Markdown",
            disable_web_page_preview=False # Оставляем превью для красоты
        )
        logger.info(f"Пост успешно опубликован! Message ID: {message.message_id}")
        return message.message_id
    except Exception as e:
        logger.error(f"Ошибка при отправке сообщения в Telegram: {e}")
        # Если legacy Markdown упал (например, из-за непарных символов), попробуем отправить чистым текстом
        try:
            logger.info("Попытка отправить пост без форматирования (из-за ошибки разметки)...")
            plain_text = text.replace("**", "").replace("{link}", url).replace("{{link}}", url) + f"\n\nИсточник: {url}"
            message = bot.send_message(
                chat_id=config.TELEGRAM_CHANNEL_ID,
                text=plain_text,
                disable_web_page_preview=False
            )
            return message.message_id
        except Exception as ex:
            logger.error(f"Критическая ошибка при отправке чистого текста: {ex}")
            return None

if __name__ == "__main__":
    # Тест отправки (нужно заполнить .env перед запуском)
    if bot:
        print("Тестирование отправки сообщения...")
        test_text = "**Тестовый пост**\n\nЭто проверка автопостинга ИИ-новостей. {link}"
        test_url = "https://example.com"
        msg_id = post_to_channel(test_text, test_url)
        print(f"Результат отправки: ID={msg_id}")
