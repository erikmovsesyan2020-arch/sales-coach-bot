"""
AI Sales Coach Bot — MVP (Groq — бесплатно!)
Анализирует звонки менеджеров по продажам с помощью AI
"""

import os
import logging
import tempfile
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from groq import Groq

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

client = Groq(api_key=os.environ["GROQ_API_KEY"])
TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]

SALES_COACH_PROMPT = """Ты — AI Sales Coach, лучший наставник по продажам в мире.

Ты анализируешь расшифровки звонков менеджеров по продажам и даёшь 
детальную, конкретную обратную связь.

Твоя методология основана на:
- Система Джордана Белфорта (Straight Line Persuasion)
- SPIN Selling (Нил Рэкхем)
- Challenger Sale (Диксон и Адамсон)
- Техники Сергея Филиппова
- Современные техники переговоров и управления возражениями

ФОРМАТ ОТВЕТА (строго соблюдай структуру):

🎯 ОБЩАЯ ОЦЕНКА ЗВОНКА
Оценка: [X/10]
Одно предложение — общий вывод о качестве звонка.

---

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

---

🚨 КРИТИЧЕСКИЕ ОШИБКИ (топ-3)

Ошибка 1:
ОШИБКА: [точная цитата или описание момента]
ПОЧЕМУ ЭТО ПЛОХО: [объяснение]
КАК НАДО БЫЛО: [конкретная альтернативная фраза]

Ошибка 2:
ОШИБКА: [точная цитата или описание момента]
ПОЧЕМУ ЭТО ПЛОХО: [объяснение]
КАК НАДО БЫЛО: [конкретная альтернативная фраза]

Ошибка 3:
ОШИБКА: [точная цитата или описание момента]
ПОЧЕМУ ЭТО ПЛОХО: [объяснение]
КАК НАДО БЫЛО: [конкретная альтернативная фраза]

---

💡 РАЗБОР КЛЮЧЕВЫХ МОМЕНТОВ

Момент 1: "[цитата]"
Что произошло: [анализ]
Лучший вариант: "[как надо было сказать]"

Момент 2: "[цитата]"
Что произошло: [анализ]
Лучший вариант: "[как надо было сказать]"

Момент 3: "[цитата]"
Что произошло: [анализ]
Лучший вариант: "[как надо было сказать]"

---

📈 ТОП-3 РЕКОМЕНДАЦИИ ДЛЯ РОСТА

1. [Конкретное действие с примером]
2. [Конкретное действие с примером]
3. [Конкретное действие с примером]

---

🏆 ИТОГ

Сильные стороны: [2-3 пункта]
Главное что нужно проработать: [1 главный фокус]
Следующий шаг: [конкретное упражнение]

Будь конкретным и честным. Твоя цель — реальный рост навыков менеджера."""


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "👋 Привет! Я AI Sales Coach.\n\n"
        "Я анализирую твои звонки и помогаю стать лучшим менеджером по продажам.\n\n"
        "Как использовать:\n"
        "Просто отправь мне голосовое сообщение или аудиофайл (mp3, wav, m4a, ogg)\n\n"
        "И я:\n"
        "✅ Переведу речь в текст\n"
        "✅ Проанализирую разговор по 8 критериям\n"
        "✅ Найду ошибки и объясню почему\n"
        "✅ Покажу как надо было ответить\n"
        "✅ Дам оценку и рекомендации\n\n"
        "Отправляй свой первый звонок — начнём! 🚀"
    )
    await update.message.reply_text(text)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "📖 Инструкция\n\n"
        "Поддерживаемые форматы:\n"
        "• Голосовые сообщения Telegram\n"
        "• MP3, WAV, M4A, OGG\n"
        "• Максимальный размер: 25 МБ\n\n"
        "Методология анализа:\n"
        "Jordan Belfort • SPIN • Challenger Sale • Сергей Филиппов\n\n"
        "Просто отправь аудио!"
    )
    await update.message.reply_text(text)


async def handle_audio(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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

    status_msg = await update.message.reply_text(
        "⏳ Получил аудио! Начинаю анализ...\n\n"
        "🎙️ Шаг 1/3: Транскрибирую речь в текст..."
    )

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=f".{file_ext}", delete=False) as tmp:
            await file.download_to_drive(tmp.name)
            tmp_path = tmp.name

        # ШАГ 1: Транскрипция через Groq Whisper
        transcript = transcribe_audio(tmp_path, file_ext)

        if not transcript or len(transcript.strip()) < 30:
            await status_msg.edit_text(
                "❌ Не удалось распознать речь.\n"
                "Убедись что в записи есть чёткий голос и попробуй снова."
            )
            return

        await status_msg.edit_text(
            "✅ Текст готов!\n\n"
            "🧠 Шаг 2/3: AI анализирует разговор по 8 критериям...\n\n"
            "(Это займёт 20-40 секунд)"
        )

        # ШАГ 2: Анализ через Llama на Groq
        analysis = analyze_call(transcript)

        await status_msg.edit_text(
            "✅ Анализ завершён!\n\n"
            "📋 Шаг 3/3: Отправляю отчёт..."
        )

        # Транскрипция
        if len(transcript) < 3000:
            await update.message.reply_text(
                f"📝 ТРАНСКРИПЦИЯ ЗВОНКА:\n\n{transcript[:2900]}"
            )

        # Анализ (разбиваем если длинный)
        await send_long_message(update, f"🎯 АНАЛИЗ ЗВОНКА\n\n{analysis}")
        await status_msg.delete()

    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await status_msg.edit_text(
            f"❌ Произошла ошибка:\n{str(e)[:300]}\n\nПопробуй ещё раз."
        )
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass


def transcribe_audio(file_path: str, file_ext: str) -> str:
    """Транскрибирует аудио через Groq Whisper"""
    with open(file_path, "rb") as audio_file:
        response = client.audio.transcriptions.create(
            model="whisper-large-v3",
            file=(f"audio.{file_ext}", audio_file),
            language="ru",
            response_format="text"
        )
    return response


def analyze_call(transcript: str) -> str:
    """Анализирует транскрипцию через Llama на Groq"""
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        max_tokens=4000,
        messages=[
            {"role": "system", "content": SALES_COACH_PROMPT},
            {"role": "user", "content": (
                f"Проанализируй следующий звонок менеджера по продажам:\n\n"
                f"ТРАНСКРИПЦИЯ ЗВОНКА:\n\n"
                f"{transcript}\n\n"
                f"Дай детальный анализ по указанному формату. "
                f"Ссылайся на реальные фразы из разговора."
            )}
        ]
    )
    return response.choices[0].message.content


async def send_long_message(update: Update, text: str, max_length: int = 4000) -> None:
    """Отправляет длинное сообщение, разбивая на части"""
    if len(text) <= max_length:
        await update.message.reply_text(text)
        return

    while len(text) > 0:
        if len(text) <= max_length:
            await update.message.reply_text(text)
            break
        # Ищем последний перенос строки в пределах лимита
        split_at = text[:max_length].rfind('\n')
        if split_at == -1:
            split_at = max_length
        await update.message.reply_text(text[:split_at])
        text = text[split_at:].lstrip('\n')


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "🎙️ Отправь мне аудиофайл или голосовое сообщение с записью звонка.\n\n"
        "Нужна помощь? /help"
    )


def main() -> None:
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO | filters.VIDEO_NOTE, handle_audio))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    print("🚀 AI Sales Coach Bot запущен!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
