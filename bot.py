import os, logging, tempfile
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler
from groq import Groq

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
client = Groq(api_key=os.environ["GROQ_API_KEY"])
TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
CHOOSING_NICHE, WAITING_AUDIO = range(2)
NICHES = ["Логистика"]

PROMPT = """Ты — AI Sales Coach. Методология: Jordan Belfort, Joe Girard, Movsesian Erik, Сергей Филиппов.
{niche_context}
Анализируй звонок по формату:
🎯 ОБЩАЯ ОЦЕНКА [X/10]
📊 АНАЛИЗ (8 критериев с оценками)
🚨 ТОП-3 ОШИБКИ (цитата, почему плохо, как надо)
💡 КЛЮЧЕВЫЕ МОМЕНТЫ
📈 ТОП-3 РЕКОМЕНДАЦИИ
🏆 ИТОГ"""

NICHES_CTX = {"Логистика": "Ниша: грузоперевозки и логистика. Учитывай специфику: маршруты, сроки, фрахт, объёмы отправок."}

async def start(update, context):
    kb = [[n] for n in NICHES]
    await update.message.reply_text("👋 Привет! Я AI Sales Coach.\n\nВ какой области вы работаете?", reply_markup=ReplyKeyboardMarkup(kb, one_time_keyboard=True, resize_keyboard=True))
    return CHOOSING_NICHE

async def choose_niche(update, context):
    niche = update.message.text
    if niche not in NICHES:
        kb = [[n] for n in NICHES]
        await update.message.reply_text("Выбери из списка 👇", reply_markup=ReplyKeyboardMarkup(kb, one_time_keyboard=True, resize_keyboard=True))
        return CHOOSING_NICHE
    context.user_data["niche"] = niche
    await update.message.reply_text(f"Отлично, ниша: {niche} 💼\n\nОтправь запись звонка — голосовое или аудиофайл (mp3, wav, m4a, ogg)\n\nМетодология: Jordan Belfort • Joe Girard • Movsesian Erik • Сергей Филиппов", reply_markup=ReplyKeyboardRemove())
    return WAITING_AUDIO

async def handle_audio(update, context):
    if update.message.voice:
        file = await update.message.voice.get_file(); ext = "ogg"
    elif update.message.audio:
        file = await update.message.audio.get_file(); ext = "mp3"
    else:
        await update.message.reply_text("❌ Отправь аудиофайл или голосовое сообщение.")
        return WAITING_AUDIO
    niche = context.user_data.get("niche", "Логистика")
    niche_ctx = NICHES_CTX.get(niche, "")
    status = await update.message.reply_text("⏳ Получил! Транскрибирую речь...")
    tmp = None
    try:
        with tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False) as f:
            await file.download_to_drive(f.name); tmp = f.name
        with open(tmp, "rb") as af:
            transcript = client.audio.transcriptions.create(model="whisper-large-v3", file=(f"audio.{ext}", af), language="ru", response_format="text")
        if not transcript or len(transcript.strip()) < 30:
            await status.edit_text("❌ Не удалось распознать речь. Попробуй снова.")
            return WAITING_AUDIO
        await status.edit_text("✅ Текст готов!\n🧠 Анализирую по 8 критериям...")
        prompt = PROMPT.format(niche_context=niche_ctx)
        response = client.chat.completions.create(model="llama-3.3-70b-versatile", max_tokens=4000, messages=[{"role":"system","content":prompt},{"role":"user","content":f"Проанализируй звонок:\n\n{transcript}"}])
        analysis = response.choices[0].message.content
        await status.delete()
        if len(transcript) < 3000:
            await update.message.reply_text(f"📝 ТРАНСКРИПЦИЯ:\n\n{transcript[:2900]}")
        text = f"🎯 АНАЛИЗ ЗВОНКА [{niche}]\n\n{analysis}"
        while text:
            if len(text) <= 4000:
                await update.message.reply_text(text); break
            split = text[:4000].rfind('\n')
            if split == -1: split = 4000
            await update.message.reply_text(text[:split]); text = text[split:].lstrip('\n')
        await update.message.reply_text("Хочешь разобрать ещё звонок? Отправляй! 🎙️\n\nИли /start чтобы сменить область.")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")
    finally:
        if tmp:
            try: os.unlink(tmp)
            except: pass
    return WAITING_AUDIO

async def handle_text(update, context):
    await update.message.reply_text("🎙️ Отправь аудиофайл или голосовое сообщение.\nИли /start чтобы начать заново.")
    return WAITING_AUDIO

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    conv = ConversationHandler(entry_points=[CommandHandler("start", start)], states={CHOOSING_NICHE:[MessageHandler(filters.TEXT & ~filters.COMMAND, choose_niche)], WAITING_AUDIO:[MessageHandler(filters.VOICE | filters.AUDIO, handle_audio), MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text)]}, fallbacks=[CommandHandler("start", start)])
    app.add_handler(conv)
    print("🚀 AI Sales Coach Bot запущен!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
