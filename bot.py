import os, logging, tempfile
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler
from groq import Groq

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
client = Groq(api_key=os.environ["GROQ_API_KEY"])
TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
CHOOSING_NICHE, WAITING_AUDIO = range(2)
NICHES = ["Logistika"]
NICHES_CTX = {"Logistika": "Nisha: gruzoperevozki i logistika. Marshruty, sroki, fraht, obemy otpravok."}

PROMPT = (
    "Ty - AI Sales Coach, ekspert po prodazham.\n\n"
    "{niche_context}\n\n"
    "OPREDELI ROLI:\n"
    "Prodazhnik - zvonit pervim, predlagaet uslugu, nazyvaet tsenu, zadaet voprosy o potrebnostyah.\n"
    "Klient - vozrazhaet, uklonaetsya, govorit podomayu ili otpravte na pochtu.\n\n"
    "METODOLOGIYA:\n"
    "Belfort - pryamolineynaya sistema, tri desyatki uverennosti, tonalnost golosa.\n"
    "SPIN - Situation Problem Implication Need-payoff voprosy.\n"
    "Filippov Sales 3.0 - prodazha cherez tsennost, pravilo treh da pered zakrytiem.\n\n"
    "OTVET TOLKO NA RUSSKOM YAZYKE!\n\n"
    "FORMAT OTVETA:\n\n"
    "OTSENKA ZVONKA: [X/10]\n"
    "[glavniy vyvod 1-2 predlozheniya]\n\n"
    "KTO EST KTO\n"
    "Prodazhnik: [kak opredelil]\n"
    "Klient: [kak opredelil]\n"
    "Emotsii klienta: [chto schital po slovam]\n\n"
    "RAZBOR PO KRITERIYAM\n\n"
    "1. Viyavlenie potrebnostey [X/10]\n"
    "Horosho: [konkretno]\n"
    "Upushcheno: [konkretno]\n"
    "Po SPIN: [chto nado bylo sprosit]\n\n"
    "2. Rabota s vozrazheniyami [X/10]\n"
    "Horosho: [konkretno]\n"
    "Upushcheno: [konkretno]\n"
    "Po Belforu: [kak nado bylo otvetit]\n\n"
    "3. Uverennost i ton [X/10]\n"
    "Horosho: [konkretno]\n"
    "Upushcheno: [konkretno]\n\n"
    "4. Struktura prodazhi [X/10]\n"
    "Horosho: [konkretno]\n"
    "Upushcheno: [konkretno]\n"
    "Po Filippovu: [chto primenit]\n\n"
    "5. Kachestvo voprosov [X/10]\n"
    "Horosho: [konkretno]\n"
    "Upushcheno: [konkretno]\n\n"
    "6. Initsiativa i dozhim [X/10]\n"
    "Horosho: [konkretno]\n"
    "Upushcheno: [konkretno]\n\n"
    "7. Rabota s tsenoy [X/10]\n"
    "Horosho: [konkretno]\n"
    "Upushcheno: [konkretno]\n\n"
    "8. Signaly klienta [X/10]\n"
    "Horosho: [konkretno]\n"
    "Upushcheno: [konkretno]\n\n"
    "TOP-3 OSHIBKI\n\n"
    "Oshibka 1: [tsitata iz razgovora]\n"
    "Pochemu ploho: [obyasnenie]\n"
    "Kak nado bylo: [konkretnaya fraza]\n\n"
    "Oshibka 2: [tsitata iz razgovora]\n"
    "Pochemu ploho: [obyasnenie]\n"
    "Kak nado bylo: [konkretnaya fraza]\n\n"
    "Oshibka 3: [tsitata iz razgovora]\n"
    "Pochemu ploho: [obyasnenie]\n"
    "Kak nado bylo: [konkretnaya fraza]\n\n"
    "3 SHAGA DLYA ROSTA\n"
    "1. [deystvie + primer frazy]\n"
    "2. [deystvie + primer frazy]\n"
    "3. [deystvie + primer frazy]\n\n"
    "ITOG\n"
    "Sila menedzhera: [1-2 punkta]\n"
    "Glavniy fokus: [odno konkretnoe deystvie]\n"
)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    kb = [[n] for n in NICHES]
    await update.message.reply_text(
        "Privet! Ya AI Sales Coach.\n\nV kakoy oblasti vy rabotaete?",
        reply_markup=ReplyKeyboardMarkup(kb, one_time_keyboard=True, resize_keyboard=True)
    )
    return CHOOSING_NICHE


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "AI Sales Coach analiziruet zapisi holodnyh zvonkov.\n\n"
        "Posle analiza ty poluchish:\n"
        "- Otsenku zvonka po 8 kriteriyam\n"
        "- Razbor oshibok s tsitatami\n"
        "- Konkretnye frazy kak nado bylo otvetit\n"
        "- Analiz emotsiy klienta\n"
        "- Rekomendatsii dlya rosta\n\n"
        "Metodologiya: Jordan Belfort, SPIN Selling, Sergey Filippov, Movsesian Erik\n\n"
        "Formaty: golosovye soobsheniya, MP3, WAV, M4A, OGG do 25 MB\n\n"
        "Prosto otprav audio!"
    )


async def choose_niche(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    niche = update.message.text
    if niche not in NICHES:
        kb = [[n] for n in NICHES]
        await update.message.reply_text(
            "Vyberi oblast iz spiska",
            reply_markup=ReplyKeyboardMarkup(kb, one_time_keyboard=True, resize_keyboard=True)
        )
        return CHOOSING_NICHE
    context.user_data["niche"] = niche
    await update.message.reply_text(
        "Otlichno, nisha: " + niche + "\n\nOtprav zapis zvonka - golosovoe ili audiofayl.\n\nNuzhna pomosh? /help",
        reply_markup=ReplyKeyboardRemove()
    )
    return WAITING_AUDIO


async def handle_audio(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.voice:
        file = await update.message.voice.get_file()
        ext = "ogg"
    elif update.message.audio:
        file = await update.message.audio.get_file()
        ext = "mp3"
    else:
        await update.message.reply_text("Otprav audiofayl ili golosovoe soobshenie.")
        return WAITING_AUDIO

    niche = context.user_data.get("niche", "Logistika")
    niche_ctx = NICHES_CTX.get(niche, "")
    status = await update.message.reply_text("Poluchil zapis! Transkribiruyu rech...")
    tmp = None
    try:
        with tempfile.NamedTemporaryFile(suffix="." + ext, delete=False) as f:
            await file.download_to_drive(f.name)
            tmp = f.name
        with open(tmp, "rb") as af:
            transcript = client.audio.transcriptions.create(
                model="whisper-large-v3",
                file=("audio." + ext, af),
                language="ru",
                response_format="text"
            )
        if not transcript or len(transcript.strip()) < 30:
            await status.edit_text("Ne udalos raspoznat rech. Poprobuy snova.")
            return WAITING_AUDIO
        await status.edit_text("Tekst gotov! Analiziruyu po metodologii Belfora, SPIN i Filippova...")
        prompt = PROMPT.format(niche_context=niche_ctx)
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            max_tokens=4000,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": "Proanaliziruy etot zvonok:\n\n" + str(transcript)}
            ]
        )
        analysis = response.choices[0].message.content
        await status.delete()
        if len(str(transcript)) < 3000:
            await update.message.reply_text("TRANSKRIPTSIYA:\n\n" + str(transcript)[:2900])
        text = "ANALIZ ZVONKA [" + niche + "]\n\n" + analysis
        while text:
            if len(text) <= 4000:
                await update.message.reply_text(text)
                break
            split = text[:4000].rfind("\n")
            if split == -1:
                split = 4000
            await update.message.reply_text(text[:split])
            text = text[split:].lstrip("\n")
        await update.message.reply_text("Hochesh razobrат eshche zvonok? Otpravlyay!\nIli /start chtoby smenit oblast.")
    except Exception as e:
        logging.error("Oshibka: " + str(e))
        await update.message.reply_text("Oshibka: " + str(e)[:200])
    finally:
        if tmp:
            try:
                os.unlink(tmp)
            except Exception:
                pass
    return WAITING_AUDIO


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "Otprav audiofayl ili golosovoe soobshenie.\n"
        "Ili /start chtoby nachat zanovo.\n"
        "Ili /help dlya spravki."
    )
    return WAITING_AUDIO


def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            CHOOSING_NICHE: [MessageHandler(filters.TEXT & ~filters.COMMAND, choose_niche)],
            WAITING_AUDIO: [
                MessageHandler(filters.VOICE | filters.AUDIO, handle_audio),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text)
            ]
        },
        fallbacks=[CommandHandler("start", start)]
    )
    app.add_handler(conv)
    app.add_handler(CommandHandler("help", help_command))
    print("AI Sales Coach Bot zapushen!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
