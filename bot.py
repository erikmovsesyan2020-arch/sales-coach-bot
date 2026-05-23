import os, logging, tempfile
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler
from groq import Groq

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
client = Groq(api_key=os.environ["GROQ_API_KEY"])
TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
CHOOSING_NICHE, WAITING_AUDIO = range(2)
NICHES = ['Логистика']
NICHES_CTX = {'Логистика': 'Ниша: грузоперевозки и логистика. Маршруты, сроки, фрахт, объемы.'}
PROMPT = 'Ты - AI Sales Coach, эксперт по продажам мирового уровня.\n\n{niche_context}\n\nОпредели роли: Продажник - звонит первым, предлагает услугу, называет цену. Клиент - возражает, уклоняется, говорит подумаю.\n\nМетодология: Белфорт (три десятки уверенности), SPIN (ситуация/проблема/импликация/направление), Филиппов Sales 3.0.\n\nФОРМАТ ОТВЕТА:\n\nОЦЕНКА ЗВОНКА: [X/10]\n[главный вывод]\n\nКТО ЕСТЬ КТО\nПродажник: [как определил]\nКлиент: [как определил]\nЭмоции: [что считал]\n\nРАЗБОР ПО КРИТЕРИЯМ\n\n1. Выявление потребностей [X/10]\nХорошо: [конкретно]\nУпущено: [конкретно]\nПо SPIN: [что надо спросить]\n\n2. Работа с возражениями [X/10]\nХорошо: [конкретно]\nУпущено: [конкретно]\nПо Белфорту: [как надо было ответить]\n\n3. Уверенность и тон [X/10]\nХорошо: [конкретно]\nУпущено: [конкретно]\n\n4. Структура продажи [X/10]\nХорошо: [конкретно]\nУпущено: [конкретно]\nПо Филиппову: [что применить]\n\n5. Качество вопросов [X/10]\nХорошо: [конкретно]\nУпущено: [конкретно]\n\n6. Инициатива и дожим [X/10]\nХорошо: [конкретно]\nУпущено: [конкретно]\n\n7. Работа с ценой [X/10]\nХорошо: [конкретно]\nУпущено: [конкретно]\n\n8. Сигналы клиента [X/10]\nХорошо: [конкретно]\nУпущено: [конкретно]\n\nТОП-3 ОШИБКИ\n\nОшибка 1: [цитата]\nПочему плохо: [объяснение]\nКак надо было: [фраза]\n\nОшибка 2: [цитата]\nПочему плохо: [объяснение]\nКак надо было: [фраза]\n\nОшибка 3: [цитата]\nПочему плохо: [объяснение]\nКак надо было: [фраза]\n\n3 ШАГА ДЛЯ РОСТА\n1. [действие + пример]\n2. [действие + пример]\n3. [действие + пример]\n\nИТОГ\nСила менеджера: [1-2 пункта]\nГлавный фокус: [одно действие]\n'


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    kb = [[n] for n in NICHES]
    await update.message.reply_text('Привет! Я AI Sales Coach.\n\nВ какой области вы работаете?', reply_markup=ReplyKeyboardMarkup(kb, one_time_keyboard=True, resize_keyboard=True))
    return CHOOSING_NICHE


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text('Бот анализирует записи звонков и переговоров.\n\nПосле анализа ты получишь:\n- Оценка звонка по 8 критериям\n- Разбор ошибок с цитатами\n- Конкретные фразы как надо было ответить\n- Анализ эмоций клиента\n- Рекомендации для роста\n\nМетодология: Jordan Belfort, SPIN, Сергей Филиппов, Movsesian Erik\n\nФорматы: голосовые, MP3, WAV, M4A, OGG до 25 МБ\n\nПросто отправь аудио!')


async def choose_niche(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    niche = update.message.text
    if niche not in NICHES:
        kb = [[n] for n in NICHES]
        await update.message.reply_text('Выбери область из списка', reply_markup=ReplyKeyboardMarkup(kb, one_time_keyboard=True, resize_keyboard=True))
        return CHOOSING_NICHE
    context.user_data["niche"] = niche
    await update.message.reply_text('Отлично, ниша: ' + niche + '\n\nОтправь запись звонка - голосовое или аудиофайл.\n\nНужна помощь? /help', reply_markup=ReplyKeyboardRemove())
    return WAITING_AUDIO


async def handle_audio(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.voice:
        file = await update.message.voice.get_file()
        ext = "ogg"
    elif update.message.audio:
        file = await update.message.audio.get_file()
        ext = "mp3"
    else:
        await update.message.reply_text('Отправь аудиофайл или голосовое сообщение.')
        return WAITING_AUDIO
    niche = context.user_data.get("niche", 'Логистика')
    niche_ctx = NICHES_CTX.get(niche, "")
    status = await update.message.reply_text('Получил запись! Транскрибирую речь...')
    tmp = None
    try:
        with tempfile.NamedTemporaryFile(suffix="." + ext, delete=False) as f:
            await file.download_to_drive(f.name)
            tmp = f.name
        with open(tmp, "rb") as af:
            transcript = client.audio.transcriptions.create(model="whisper-large-v3", file=("audio." + ext, af), language="ru", response_format="text")
        if not transcript or len(transcript.strip()) < 30:
            await status.edit_text('Не удалось распознать речь. Попробуй снова.')
            return WAITING_AUDIO
        await status.edit_text('Текст готов! Анализирую по методологии Белфорта, SPIN и Филиппова...')
        prompt = PROMPT.format(niche_context=niche_ctx)
        response = client.chat.completions.create(model="llama-3.3-70b-versatile", max_tokens=4000, messages=[{"role": "system", "content": prompt}, {"role": "user", "content": 'Проанализируй звонок:\n\n' + str(transcript)}])
        analysis = response.choices[0].message.content
        await status.delete()
        if len(str(transcript)) < 3000:
            await update.message.reply_text('ТРАНСКРИПЦИЯ:\n\n' + str(transcript)[:2900])
        text = 'АНАЛИЗ ЗВОНКА [' + niche + "]\n\n" + analysis
        while text:
            if len(text) <= 4000:
                await update.message.reply_text(text)
                break
            split = text[:4000].rfind("\n")
            if split == -1:
                split = 4000
            await update.message.reply_text(text[:split])
            text = text[split:].lstrip("\n")
        await update.message.reply_text('Хочешь разобрать еще звонок? Отправляй!\nИли /start чтобы сменить область.')
    except Exception as e:
        logging.error("Error: " + str(e))
        await update.message.reply_text('Ошибка: ' + str(e)[:200])
    finally:
        if tmp:
            try:
                os.unlink(tmp)
            except Exception:
                pass
    return WAITING_AUDIO


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text('Отправь аудиофайл или голосовое.\nИли /start чтобы начать заново.\nИли /help для справки.')
    return WAITING_AUDIO


def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    conv = ConversationHandler(entry_points=[CommandHandler("start", start)], states={CHOOSING_NICHE: [MessageHandler(filters.TEXT & ~filters.COMMAND, choose_niche)], WAITING_AUDIO: [MessageHandler(filters.VOICE | filters.AUDIO, handle_audio), MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text)]}, fallbacks=[CommandHandler("start", start)])
    app.add_handler(conv)
    app.add_handler(CommandHandler("help", help_command))
    print("Bot started!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
