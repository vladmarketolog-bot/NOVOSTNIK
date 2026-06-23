import json
import logging
import google.generativeai as genai
import config

# Настройка логирования
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Инициализируем Gemini API
if config.GEMINI_API_KEY:
    genai.configure(api_key=config.GEMINI_API_KEY)
else:
    logger.warning("GEMINI_API_KEY не установлен! Бот не сможет обрабатывать новости.")

def analyze_and_format_article(title: str, text: str, source_name: str) -> dict:
    """
    Отправляет заголовок и текст статьи в Gemini API.
    ИИ оценивает релевантность статьи маркетингу, LTV и Retention,
    и в случае успеха генерирует готовый пост в стиле блогера/обзорщика.
    
    Возвращает словарь:
    {
        "is_relevant": bool,
        "relevance_score": int (0-100),
        "post_text": str (готовый текст на русском с форматированием) или None,
        "rejection_reason": str или None
    }
    """
    if not config.GEMINI_API_KEY:
        logger.error("Запрос к Gemini невозможен: отсутствует API ключ.")
        return {"is_relevant": False, "relevance_score": 0, "post_text": None, "rejection_reason": "API key missing"}

    # Обрезаем текст статьи, чтобы уложиться в контекст и лимиты (примерно 15 000 символов достаточно)
    truncated_text = text[:15000]

    system_instruction = (
        "Ты — профессиональный ИИ-агент, ведущий Telegram-канал о маркетинге, удержании клиентов (Retention) и пожизненной ценности клиента (LTV). "
        "Твоя задача — проанализировать англоязычную статью и решить, подходит ли она для канала. "
        "Если статья релевантна, напиши по ней интересный, вовлекающий пост-обзор на русском языке."
    )

    prompt = f"""
Проанализируй следующую статью:
Название: {title}
Источник: {source_name}
Текст статьи:
{truncated_text}

Инструкции по анализу:
1. Статья должна быть строго связана с темами: маркетинг (особенно growth-маркетинг, продуктовый маркетинг), LTV (Lifetime Value), Retention (удержание клиентов), воронки продаж, лояльность клиентов или продуктовая аналитика.
2. Если статья не связана с этими темами (например, общие новости технологий, политика, или просто новости AI без привязки к маркетингу), отметь её как нерелевантную.
3. Оцени качество статьи и её инсайты от 0 до 100 (relevance_score). Нам нужны только качественные материалы с цифрами, кейсами или сильной теорией.

Инструкции по написанию поста (если статья релевантна):
1. Напиши пост полностью на русском языке.
2. Стиль: Новостной редактор, блогер-обзорщик, эксперт. Текст должен быть живым, уверенным, без канцеляризмов и лишней "воды", с легкой иронией и вашей авторской оценкой.
3. Расшифровка терминов: Обязательно разжевывай и поясняй на русском языке все англоязычные профессиональные термины и аббревиатуры при их первом упоминании в тексте (например: CPG -> CPG (товары повседневного спроса), ROI -> ROI (окупаемость инвестиций), LTV -> LTV (пожизненная ценность клиента), Retention -> Retention (удержание клиентов), CAC -> CAC (стоимость привлечения клиента)).
4. Структура поста:
   - ⚡️ **Цепляющий заголовок** (выражает главную суть новости или инсайта).
   - **Короткое интро**: Вводная часть (о чем речь, какая компания или исследование).
   - **Главные инсайты / цифры**: Используй простые списки (`-`) для структурирования главных фактов и цифр. Форматирование должно быть чистым, строгим и удобным для быстрого восприятия новости, без перегрузки лишними эмодзи и символами.
   - **Мой комментарий** (или **Моё мнение**): Раздел должен называться именно так. Напиши его от первого лица (используй 'я', 'мой', 'на мой взгляд'). Объясни практическую ценность этой новости для маркетологов, LTV или Retention. Дай совет.
   - В самом конце обязательно добавь плейсхолдер `{{link}}` для вставки ссылки на оригинальную статью.
5. Никогда не вставляй в текст поста реальные веб-ссылки (URL) самостоятельно. Используй для этого исключительно плейсхолдер `{{link}}`.
6. Используй эмодзи для улучшения читаемости (но умеренно и только по делу, не перенасыщая текст).
7. Форматируй важные мысли жирным шрифтом (используй markdown `**текст**`).

Ответ должен быть строго в формате JSON со следующей структурой:
{{
  "is_relevant": true/false,
  "relevance_score": 85,
  "post_text": "Текст сгенерированного поста на русском...",
  "rejection_reason": "Причина отклонения (если is_relevant = false)"
}}
"""

    try:
        # Настраиваем вывод в формате JSON
        generation_config = {
            "response_mime_type": "application/json",
            "temperature": 0.3, # Низкая температура для более строгой логики и следования инструкциям
        }

        model = genai.GenerativeModel(
            model_name=config.GEMINI_MODEL,
            generation_config=generation_config,
            system_instruction=system_instruction
        )

        response = model.generate_content(prompt)
        
        # Парсим JSON ответ
        result = json.loads(response.text)
        
        # Гарантируем наличие необходимых ключей
        if "is_relevant" not in result:
            result["is_relevant"] = False
        if "relevance_score" not in result:
            result["relevance_score"] = 0
        if "post_text" not in result:
            result["post_text"] = None
        if "rejection_reason" not in result:
            result["rejection_reason"] = "Unknown logic error in Gemini response structure"

        return result

    except Exception as e:
        logger.error(f"Ошибка при работе с Gemini API или парсинге ответа: {e}")
        return {
            "is_relevant": False,
            "relevance_score": 0,
            "post_text": None,
            "rejection_reason": f"Error: {str(e)}"
        }

# Для тестирования модуля вручную
if __name__ == "__main__":
    test_title = "How Slack improved user retention by 15% using personalized onboarding"
    test_text = """
    In 2025, Slack implemented a series of onboarding experiments focused on customer retention. 
    By introducing personalized setup sequences based on user job roles (e.g., engineering, sales, marketing), 
    they managed to increase the 7-day user retention rate by 15%.
    The team found that users who integrated at least two third-party applications in their first 48 hours 
    had a 40% higher lifetime value (LTV). Thus, the onboarding was redesigned to highlight integrations immediately.
    Marketing campaigns were also realigned to attract users specifically interested in these integrations, 
    reducing customer acquisition cost (CAC) and driving overall retention upward.
    """
    print("Запуск тестового анализа...")
    res = analyze_and_format_article(test_title, test_text, "Slack Tech Blog")
    print(json.dumps(res, indent=2, ensure_ascii=False))
