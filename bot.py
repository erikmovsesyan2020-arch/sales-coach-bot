import os, logging, tempfile
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler
from groq import Groq

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
client = Groq(api_key=os.environ["GROQ_API_KEY"])
TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
CHOOSING_NICHE, WAITING_AUDIO = range(2)
NICHES = ["Логистика"]
NICHES_CTX = {"Логистика": "Ниша: грузоперевозки и логистика. Учитывай специфику: маршруты, сроки доставки, стоимость фрахта, объёмы и регулярность отправок."}
PROMPT = """Ты — AI Sales Coach, эксперт по продажам мирового уровня.

{niche_context}

ОПРЕДЕЛИ РОЛИ: Продажник — звонит первым, предлагает услугу, называет цену, задаёт вопросы о потребностях. Клиент — возражает, уклоняется, говорит "подумаю", "отправьте на почту".

МЕТОДОЛОГИЯ:
- Белфорт "Метод Волка": прямолинейная система, три десятки уверенности, тональность голоса
- Рэкхем "SPIN": Situation, Problem, Implication, Need-payoff вопросы
- Филиппов "Sales 3.0": продажа через ценность, правило трёх да перед закрытием

ЭМОЦИИ КЛИЕНТА: определяй по словам и контексту — интерес, раздражение, сомнение, готовность купить.

ФОРМАТ (пиши живо, с цитатами из разговора):

ОЦЕНКА ЗВОНКА: [X/10]
[главный вывод 1-2 предложения]

КТО ЕСТЬ КТО
Продажник: [как определил]
Клиент: [как определил]
Эмоции клиента: [что считал]

РАЗБОР ПО КРИТЕРИЯМ

1 Выявление потребностей [X/10]
Хорошо: [конкретно]
Упущено: [конкретно]
По SPIN: [что надо было спросить]

2 Работа с возражениями [X/10]
Хорошо: [конкретно]
Упущено: [конкретно]
По Белфорту: [как надо было ответить]

3 Уверенность и тон [X/10]
Хорошо: [конкретно]
Упущено: [конкретно]

4 Структура продажи [X/10]
Хорошо: [конкретно]
Упущено: [конкретно]
По Филиппову: [что применить]

5 Качество вопросов [X/10]
Хорошо: [конкретно]
Упущено: [конкретно]

6 Инициатива и дожим [X/10]
Хорошо: [конкретно]
Упущено: [конкретно]

7 Работа с ценой [X/10]
Хорошо: [конкретно]
Упущено: [конкретно]

8 Считывание сигналов клиента [X/10]
Хорошо: [конкретно]
Упущено: [конкретно]

ТОП-3 ОШИБКИ

Ошибка 1: "[цитата]"
Почему плохо: [объяснение]
Как надо было: "[конкретная фраза]"

Ошибка 2: "[цитата]"
Почему плохо: [объяснение]
Как надо было: "[конкретная фраза]"

Ошибка 3: "[цитата]"
Почему плохо: [объяснение]
Как надо было: "[конкретная фраза]"

3 ШАГА ДЛЯ РОСТА
1. [действие + пример фразы]
2. [действие + пример фразы]
3. [действие + пример фразы]

ИТОГ
Сила менеджера: [1-2 пункта]
Главный фокус: [одно конкретное действие]"""

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    kb = [[n] for n in NICHES]
    await update.message.reply_text("👋 Привет! Я AI Sales Coach — твой персональный наставник по продажам.\n\nВ какой области вы работаете?", reply_markup=ReplyKeyboardMarkup(kb, one_time_keyboard=True, resize_keyboard=True))
    return CHOOSING_NICHE

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("📖 AI Sales Coach анализирует записи холодных звонков и переговоров.\n\nПосле анализа ты получишь:\n- Оценку звонка по 8 критериям\n- Разбор ошибок с цитатами\n- Конкретные фразы — как надо было ответить\n- Анализ эмоций клиента\n- Рекомендации для роста\n\nМетодология: Jordan Belfort, SPIN Selling, Sergey Filippov, Movsesian Erik\n\nПоддерживаемые форматы: голосовые сообщения, MP3, WAV, M4A, OGG до 25 МБ\n\nПросто отправь аудио)

async def choose_niche(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    niche = update.message.text
    if niche not in NICHES:
        kb = [[n] for n in NICHES]
        await update.message.reply_text("Выбери область из списка 👇", reply_markup=ReplyKeyboardMarkup(kb, one_time_keyboard=True, resize_keyboard=True))
        return CHOOSING_NICHE
    context.user_data["niche"] = niche
    await update.message.reply_text(f"Отлично, ниша: {niche} 💼\n\nОтправь запись звонка — голосовое или аудиофайл.\n\nНужна помощь? /help", reply_markup=ReplyKeyboardRemove())
    return WAITING_AUDIO

async def handle_audio(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.voice:
        file = await update.message.voice.get_file(); ext = "ogg"
    elif update.message.audio:
        file = await update.message.audio.get_file(); ext = "mp3"
    else:
        await update.message.reply_text("Отправь аудиофайл или голосовое сообщение.")
        return WAITING_AUDIO
    niche = context.user_data.get("niche", "Логистика")
    niche_ctx = NICHES_CTX.get(niche, "")
    status = await update.message.reply_text("Получил запись! Транскрибирую речь...")
    tmp = None
    try:
        with tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False) as f:
            await file.download_to_drive(f.name); tmp = f.name
        with open(tmp, "rb") as af:
            transcript = client.audio.transcriptions.create(model="whisper-large-v3", file=(f"audio.{ext}", af), language="ru", response_format="text")
        if not transcript or len(transcript.strip()) < 30:
            await status.edit_text("Не удалось распознать речь. Попробуй снова.")
            return WAITING_AUDIO
        await status.edit_text("Текст готов! Анализирую по методологии Белфорта, SPIN и Филиппова...")
        prompt = PROMPT.format(niche_context=niche_ctx)
        response = client.chat.completions.create(model="llama-3.3-70b-versatile", max_tokens=4000, messages=[{"role":"system","content":prompt},{"role":"user","content":f"Проанализируй этот звонок:\n\n{transcript}"}])
        analysis = response.choices[0].message.content
        await status.delete()
        if len(transcript) < 3000:
            await update.message.reply_text(f"ТРАНСКРИПЦИЯ:\n\n{transcript[:2900]}")
        text = f"АНАЛИЗ ЗВОНКА [{niche}]\n\n{analysis}"
        while text:
            if len(text) <= 4000:
                await update.message.reply_text(text); break
            split = text[:4000].rfind('\n')
            if split == -1: split = 4000
            await update.message.reply_text(text[:split]); text = text[split:].lstrip('\n')
        await update.message.reply_text("Хочешь разобрать ещё звонок? Отправляй!\nИли /start чтобы сменить область.")
    except Exception as e:
        logging.error(f"Ошибка: {e}")
        await update.message.reply_text(f"Ошибка: {str(e)[:200]}")
    finally:
        if tmp:
            try: os.unlink(tmp)
            except: pass
    return WAITING_AUDIO

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Отправь аудиофайл или голосовое сообщение.\nИли /start чтобы начать заново.\nИли /help для справки.")
    return WAITING_AUDIO

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    conv = ConversationHandler(entry_points=[CommandHandler("start", start)], states={CHOOSING_NICHE:[MessageHandler(filters.TEXT & ~filters.COMMAND, choose_niche)], WAITING_AUDIO:[MessageHandler(filters.VOICE | filters.AUDIO, handle_audio), MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text)]}, fallbacks=[CommandHandler("start", start)])
    app.add_handler(conv)
    app.add_handler(CommandHandler("help", help_command))
    print("AI Sales Coach Bot запущен!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
