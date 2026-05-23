import os, logging, tempfile
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler
from groq import Groq

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
client = Groq(api_key=os.environ["GROQ_API_KEY"])
TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
CHOOSING_NICHE, WAITING_AUDIO = range(2)
NICHES = ["Logistika"]
NICHES_CTX = {"Logistika": "Nisha: gruzoperevozki i logistika. Ucityvay specifiku: marshruty, sroki dostavki, stoimost frahta, obemy i regulyarnost otpravok."}

PROMPT = """Ti - AI Sales Coach, luchshiy nastavnik po prodazham v mire.

{niche_context}

OPREDELI ROLI: Prodazhnik - zvonit pervim, predlagaet uslugu, nazyvaet tsenu, zadaet voprosy o potrebnostyah. Klient - vozrazhaet, uklonaetsya, govorit 'podomayu', 'otpravte na pochtu'.

METODOLOGIYA:
- Belfort Metod Volka: pryamolineynaya sistema, tri desyatki uverennosti, tonalnost golosa
- Rekhema SPIN: Situation, Problem, Implication, Need-payoff voprosy  
- Filippov Sales 3.0: prodazha cherez tsennost, pravilo treh da pered zakrytiem

EMOTSII KLIENTA: opredelyay po slovam - interes, razdrazhenie, somnenye, gotovnost kupit.

FORMAT (pishi zhivo, s tsitatami iz razgovora):

OTSENKA ZVONKA: [X/10]
[glavniy vyvod 1-2 predlozheniya]

KTO EST KTO
Prodazhnik: [kak opredelil]
Klient: [kak opredelil]
Emotsii klienta: [chto schital]

RAZBOR PO KRITERIYAM

1. Viyavlenie potrebnostey [X/10]
Horosho: [konkretno]
Upushcheno: [konkretno]
Po SPIN: [chto nado bylo sprosit]

2. Rabota s vozrazheniyami [X/10]
Horosho: [konkretno]
Upushcheno: [konkretno]
Po Belforu: [kak nado bylo otvetit]

3. Uverennost i ton [X/10]
Horosho: [konkretno]
Upushcheno: [konkretno]

4. Struktura prodazhi [X/10]
Horosho: [konkretno]
Upushcheno: [konkretno]
Po Filippovu: [chto primenit]

5. Kachestvo voprosov [X/10]
Horosho: [konkretno]
Upushcheno: [konkretno]

6. Initsiativa i dozhim [X/10]
Horosho: [konkretno]
Upushcheno: [konkretno]

7. Rabota s tsenoy [X/10]
Horosho: [konkretno]
Upushcheno: [konkretno]

8. Schitivanie signalov klienta [X/10]
Horosho: [konkretno]
Upushcheno: [konkretno]

TOP-3 OSHIBKI

Oshibka 1: "[tsitata]"
Pochemu ploho: [obyasnenie]
Kak nado bylo: "[konkretnaya fraza]"

Oshibka 2: "[tsitata]"
Pochemu ploho: [obyasnenie]
Kak nado bylo: "[konkretnaya fraza]"

Oshibka 3: "[tsitata]"
Pochemu ploho: [obyasnenie]
Kak nado bylo: "[konkretnaya fraza]"

3 SHAGA DLYA ROSTA
1. [deystvie + primer frazy]
2. [deystvie + primer frazy]
3. [deystvie + primer frazy]

ITOG
Sila menedzhera: [1-2 punkta]
Glavniy fokus: [odno konkretnoe deystvie]

OTVECHAY TOLKO NA RUSSKOM YAZIKE!"""

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    kb = [[n] for n in NICHES]
    await update.message.reply_text("Privet! Ya AI Sales Coach - tvoy personalnyy nastavnik po prodazham.\n\nV kakoy oblasti vy rabotaete?", reply_markup=ReplyKeyboardMarkup(kb, one_time_keyboard=True, resize_keyboard=True))
    return CHOOSING_NICHE

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("AI Sales Coach analiziruet zapisi holodnyh zvonkov i peregovorov s klientami.\n\nBot pomogaet menedzheram po prodazham nahodit oshibki, rabotat s vozrazheniyami i zakryvat bolshe sdelok.\n\nPosle analiza ty poluchish:\n- Otsenku zvonka po 8 kriteriyam\n- Razbor oshibok s tsitatami\n- Konkretnye frazy kak nado bylo otvetit\n- Analiz emotsiy klienta\n- Rekomendatsii dlya rosta\n\nMetodologiya: Jordan Belfort, SPIN Selling, Sergey Filippov, Movsesian Erik\n\nFormaty: golosovye soobsheniya, MP3, WAV, M4A, OGG do 25 MB\n\nProsto otprav audio!")

async def choose_niche(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    niche = update.message.text
    if niche not in NICHES:
        kb = [[n] for n in NICHES]
        await update.message.reply_text("Vyberi oblast iz spiska", reply_markup=ReplyKeyboardMarkup(kb, one_time_keyboard=True, resize_keyboard=True))
        return CHOOSING_NICHE
    context.user_data["niche"] = niche
    await update.message.reply_text("Otlichno, nisha: " + niche + "\n\nOtprav zapis zvonka - golosovoe ili audofayl.\n\nNuzhna pomosh? /help", reply_markup=ReplyKeyboardRemove())
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
        with tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False) as f:
            await file.download_to_drive(f.name)
            tmp = f.name
        with open(tmp, "rb") as af:
            transcript = client.audio.transcriptions.create(model="whisper-large-v3", file=(f"audio.{ext}", af), language="ru", response_format="text")
        if not transcript or len(transcript.strip()) < 30:
            await status.edit_text("Ne udalos raspoznat rech. Poprobuy snova.")
            return WAITING_AUDIO
        await status.edit_text("Tekst gotov! Analiziruyu po metodologii Belfora, SPIN i Filippova...")
        prompt = PROMPT.format(niche_context=niche_ctx)
        response = client.chat.completions.create(model="llama-3.3-70b-versatile", max_tokens=4000, messages=[{"role":"system","content":prompt},{"role":"user","content":"Proanaliziruy etot zvonok:\n\n" + transcript}])
        analysis = response.choices[0].message.content
        await status.delete()
        if len(transcript) < 3000:
            await update.message.reply_text("TRANSKRIPTSIYA:\n\n" + transcript[:2900])
        text = "ANALIZ ZVONKA [" + niche + "]\n\n" + analysis
        while text:
            if len(text) <= 4000:
                await update.message.reply_text(text)
                break
            split = text[:4000].rfind('\n')
            if split == -1:
                split = 4000
            await update.message.reply_text(text[:split])
            text = text[split:].lstrip('\n')
        await update.message.reply_text("Hochesh razobrат eshе zvonok? Otpravlyay!\nIli /start chtoby smenit oblast.")
    except Exception as e:
        logging.error(f"Oshibka: {e}")
        await update.message.reply_text("Oshibka: " + str(e)[:200])
    finally:
        if tmp:
            try:
                os.unlink(tmp)
            except:
                pass
    return WAITING_AUDIO

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Otprav audiofayl ili golosovoe soobshenie.\nIli /start chtoby nachat zanovo.\nIli /help dlya spravki.")
    return WAITING_AUDIO

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    conv = ConversationHandler(entry_points=[CommandHandler("start", start)], states={CHOOSING_NICHE:[MessageHandler(filters.TEXT & ~filters.COMMAND, choose_niche)], WAITING_AUDIO:[MessageHandler(filters.VOICE | filters.AUDIO, handle_audio), MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text)]}, fallbacks=[CommandHandler("start", start)])
    app.add_handler(conv)
    app.add_handler(CommandHandler("help", help_command))
    print("AI Sales Coach Bot zapushen!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
