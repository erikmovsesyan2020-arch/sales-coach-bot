"""
AI Sales Coach Bot — MVP
Анализирует звонки менеджеров по продажам с помощью AI
"""

import os
import logging
import tempfile
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from openai import OpenAI
import anthropic

# Настройка логов
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Клиенты API
openai_client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
anthropic_client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]

# ─── СИСТЕМНЫЙ ПРОМПТ SALES COACH ────────────────────────────────────────────

SALES_COACH_PROMPT = """Ты — AI Sales Coach, лучший наставник по продажам в мире.

Ты анализируешь расшифровки звонков менеджеров по продажам и даёшь 
детальную, конкретную обратную связь.

Твоя методология основана на:
- Система Джордана Белфорта (Straight Line Persuasion)
- SPIN Selling (Нил Рэкхем)
- Challenger Sale (Диксон и Адамсон)
- Техники Сергея Филиппова
- Современные техники переговоров и управления возражениями

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

ФОРМАТ ОТВЕТА (строго соблюдай структуру):

🎯 ОБЩАЯ ОЦЕНКА ЗВОНКА
Оценка: [X/10]
Одно предложение — общий вывод о качестве звонка.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📊 ДЕТАЛЬНЫЙ АНАЛИЗ ПО КРИТЕРИЯМ

1. Выявление потребностей [X/10]
   Что сделано: [конкретно]
   Что упущено: [конкретно]

2. Работа с возражениями [X/10]
   Что сделано: [конкретно]
   Что упущено: [конкретно]

3. Уверенность речи [X/10]
   Что сделано: [конкретно]
   Что упущено: [конкретно]

4. Структура продажи [X/10]
   Что сделано: [конкретно]
   Что упущено: [конкретно]

5. Качество вопросов [X/10]
   Что сделано: [конкретно]
   Что упущено: [конкретно]

6. Инициатива и дожим [X/10]
   Что сделано: [конкретно]
   Что упущено: [конкретно]

7. Работа с ценой [X/10]
   Что сделано: [конкретно]
   Что упущено: [конкретно]

8. Эмоциональные сигналы клиента [X/10]
   Что считано: [конкретно]
   Что пропущено: [конкретно]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🚨 КРИТИЧЕСКИЕ ОШИБКИ (топ-3)

[Для каждой ошибки:]
❌ ОШИБКА: [точная цитата из разговора или описание момента]
🔍 ПОЧЕМУ ЭТО ПЛОХО: [объяснение]
✅ КАК НАДО БЫЛО: [конкретная альтернативная фраза или действие]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

💡 РАЗБОР КЛЮЧЕВЫХ МОМЕНТОВ

[Найди 3-5 конкретных момента из разговора с таймкодом если возможно]

Момент 1: "[цитата]"
→ Что произошло: [анализ]
→ Лучший вариант: "[как надо было сказать]"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📈 ТОП-3 РЕКОМЕНДАЦИИ ДЛЯ РОСТА

1. [Конкретное действие с примером]
2. [Конкретное действие с примером]
3. [Конкретное действие с примером]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🏆 ИТОГ

Сильные стороны этого менеджера: [2-3 пункта]
Главное, что нужно проработать: [1 главный фокус]
Следующий шаг: [конкретное упражнение или задание]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Будь конкретным, честным и полезным. Не хвали то, что не заслуживает похвалы.
Твоя цель — реальный рост навыков менеджера, а не комплименты."""

# ─── КОМАНДЫ БОТА ─────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Приветственное сообщение"""
    text = (
        "👋 *Привет! Я AI Sales Coach.*\n\n"
        "Я анализирую твои звонки и помогаю стать лучшим менеджером по продажам.\n\n"
        "📤 *Как использовать:*\n"
        "Просто отправь мне:\n"
        "• 🎵 Голосовое сообщение\n"
        "• 📎 Аудиофайл (mp3, wav, m4a, ogg)\n\n"
        "И я:\n"
        "✅ Переведу речь в текст\n"
        "✅ Проанализирую каждый момент разговора\n"
        "✅ Найду ошибки и объясню почему\n"
        "✅ Покажу как надо было ответить\n"
        "✅ Дам оценку и рекомендации\n\n"
        "💡 *Лучше всего работает с записями реальных продаж.*\n\n"
        "Отправляй свой первый звонок — начнём! 🚀"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Инструкция"""
    text = (
        "📖 *Инструкция*\n\n"
        "*Поддерживаемые форматы:*\n"
        "• Голосовые сообщения Telegram\n"
        "• MP3, WAV, M4A, OGG, MP4\n"
        "• Максимальный размер: 25 МБ\n\n"
        "*Что анализирую:*\n"
        "• Выявление потребностей\n"
        "• Работа с возражениями\n"
        "• Структура продажи\n"
        "• Дожим и закрытие\n"
        "• Работа с ценой\n"
        "• Эмоциональные сигналы клиента\n"
        "• Качество вопросов\n\n"
        "*Методология:*\n"
        "Jordan Belfort • SPIN • Challenger Sale • Сергей Филиппов\n\n"
        "Просто отправь аудио ⬇️"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


# ─── ОБРАБОТКА АУДИО ──────────────────────────────────────────────────────────

async def handle_audio(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает голосовые сообщения и аудиофайлы"""
    
    # Определяем тип файла
    if update.message.voice:
        file = await update.message.voice.get_file()
        file_ext = "ogg"
    elif update.message.audio:
        file = await update.message.audio.get_file()
        file_ext = "mp3"
    elif update.message.video_note:
        file = await update.message.video_note.get_file()
        file_ext = "mp4"
    else:
        await update.message.reply_text("❌ Пожалуйста, отправь аудиофайл или голосовое сообщение.")
        return

    # Уведомляем пользователя
    status_msg = await update.message.reply_text(
        "⏳ *Получил аудио! Начинаю анализ...*\n\n"
        "🎙️ Шаг 1/3: Транскрибирую речь в текст...",
        parse_mode="Markdown"
    )

    try:
        # Скачиваем файл
        with tempfile.NamedTemporaryFile(suffix=f".{file_ext}", delete=False) as tmp:
            await file.download_to_drive(tmp.name)
            tmp_path = tmp.name

        # ШАГ 1: Транскрипция через Whisper
        transcript = await transcribe_audio(tmp_path)
        
        if not transcript or len(transcript.strip()) < 50:
            await status_msg.edit_text(
                "❌ Не удалось распознать речь. Попробуй другой файл.\n"
                "Убедись что в записи есть чёткий голос."
            )
            return

        # Обновляем статус
        await status_msg.edit_text(
            "✅ *Текст готов!*\n\n"
            "🧠 Шаг 2/3: AI анализирует разговор по 8 критериям...\n\n"
            "_(Это займёт 30-60 секунд)_",
            parse_mode="Markdown"
        )

        # ШАГ 2: Анализ через Claude
        analysis = await analyze_call(transcript)

        # Обновляем статус
        await status_msg.edit_text(
            "✅ *Анализ завершён!*\n\n"
            "📋 Шаг 3/3: Формирую отчёт...",
            parse_mode="Markdown"
        )

        # ШАГ 3: Отправляем транскрипцию (если не слишком длинная)
        if len(transcript) < 3000:
            transcript_text = (
                f"📝 *ТРАНСКРИПЦИЯ ЗВОНКА:*\n\n"
                f"```\n{transcript[:2900]}\n```"
            )
            await update.message.reply_text(transcript_text, parse_mode="Markdown")

        # Отправляем анализ (разбиваем если длинный)
        await send_long_message(update, f"🎯 *АНАЛИЗ ЗВОНКА*\n\n{analysis}")

        # Удаляем статусное сообщение
        await status_msg.delete()

    except Exception as e:
        logger.error(f"Ошибка обработки аудио: {e}")
        await status_msg.edit_text(
            "❌ *Произошла ошибка при обработке.*\n\n"
            f"Детали: `{str(e)[:200]}`\n\n"
            "Попробуй ещё раз или отправь другой файл.",
            parse_mode="Markdown"
        )
    finally:
        # Удаляем временный файл
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


async def transcribe_audio(file_path: str) -> str:
    """Транскрибирует аудио через OpenAI Whisper"""
    with open(file_path, "rb") as audio_file:
        response = openai_client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
            language="ru",  # Русский язык по умолчанию
            response_format="text"
        )
    return response


async def analyze_call(transcript: str) -> str:
    """Анализирует транскрипцию через Claude"""
    
    user_message = f"""Проанализируй следующий звонок менеджера по продажам:

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ТРАНСКРИПЦИЯ ЗВОНКА:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{transcript}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Дай детальный анализ по указанному формату. Будь конкретным — ссылайся на 
реальные фразы из разговора. Не придумывай то, чего не было в записи."""

    message = anthropic_client.messages.create(
        model="claude-opus-4-5",
        max_tokens=4000,
        system=SALES_COACH_PROMPT,
        messages=[
            {"role": "user", "content": user_message}
        ]
    )
    
    return message.content[0].text


async def send_long_message(update: Update, text: str, max_length: int = 4000) -> None:
    """Отправляет длинное сообщение, разбивая на части"""
    if len(text) <= max_length:
        await update.message.reply_text(text, parse_mode="Markdown")
        return
    
    # Разбиваем по разделителю ━━━
    parts = text.split("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    
    current_chunk = ""
    for part in parts:
        if len(current_chunk) + len(part) > max_length:
            if current_chunk:
                try:
                    await update.message.reply_text(current_chunk, parse_mode="Markdown")
                except Exception:
                    await update.message.reply_text(current_chunk)
            current_chunk = part
        else:
            current_chunk += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" + part
    
    if current_chunk:
        try:
            await update.message.reply_text(current_chunk, parse_mode="Markdown")
        except Exception:
            await update.message.reply_text(current_chunk)


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает текстовые сообщения"""
    await update.message.reply_text(
        "🎙️ Отправь мне *аудиофайл* или *голосовое сообщение* с записью звонка.\n\n"
        "Я проанализирую его и дам детальную обратную связь!\n\n"
        "Нужна помощь? /help",
        parse_mode="Markdown"
    )


# ─── ЗАПУСК БОТА ──────────────────────────────────────────────────────────────

def main() -> None:
    """Запускает бота"""
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    # Регистрируем обработчики
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO | filters.VIDEO_NOTE, handle_audio))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    print("🚀 AI Sales Coach Bot запущен!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
