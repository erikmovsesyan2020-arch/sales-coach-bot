import os, logging, tempfile
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler
from groq import Groq

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
client = Groq(api_key=os.environ["GROQ_API_KEY"])
TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
CHOOSING_NICHE, WAITING_AUDIO = range(2)
NICHES = [""]
NICHES_CTX = {"": ":   .  : ,  ,  ,    ."}
PROMPT = """  AI Sales Coach,     .

{niche_context}

 :    ,  ,  ,    .   , ,  "", "  ".

:
-  " ":  ,   ,  
-  "SPIN": Situation, Problem, Implication, Need-payoff 
-  "Sales 3.0":   ,     

 :       , , ,  .

 ( ,    ):

 : [X/10]
[  1-2 ]

  
: [ ]
: [ ]
 : [ ]

  

1   [X/10]
: []
: []
 SPIN: [   ]

2    [X/10]
: []
: []
 : [   ]

3    [X/10]
: []
: []

4   [X/10]
: []
: []
 : [ ]

5   [X/10]
: []
: []

6    [X/10]
: []
: []

7    [X/10]
: []
: []

8    [X/10]
: []
: []

-3 

 1: "[]"
 : []
  : "[ ]"

 2: "[]"
 : []
  : "[ ]"

 3: "[]"
 : []
  : "[ ]"

3   
1. [ +  ]
2. [ +  ]
3. [ +  ]


 : [1-2 ]
 : [  ]"""

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    kb = [[n] for n in NICHES]
    await update.message.reply_text(" !  AI Sales Coach      .\n\n    ?", reply_markup=ReplyKeyboardMarkup(kb, one_time_keyboard=True, resize_keyboard=True))
    return CHOOSING_NICHE

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(" AI Sales Coach      .\n\n   :\n-    8 \n-    \n-       \n-   \n-   \n\n: Jordan Belfort, SPIN Selling, Sergey Filippov, Movsesian Erik\n\n :  , MP3, WAV, M4A, OGG  25 \n\n  )

async def choose_niche(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    niche = update.message.text
    if niche not in NICHES:
        kb = [[n] for n in NICHES]
        await update.message.reply_text("    ", reply_markup=ReplyKeyboardMarkup(kb, one_time_keyboard=True, resize_keyboard=True))
        return CHOOSING_NICHE
    context.user_data["niche"] = niche
    await update.message.reply_text(f", : {niche} \n\n      .\n\n ? /help", reply_markup=ReplyKeyboardRemove())
    return WAITING_AUDIO

async def handle_audio(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.voice:
        file = await update.message.voice.get_file(); ext = "ogg"
    elif update.message.audio:
        file = await update.message.audio.get_file(); ext = "mp3"
    else:
        await update.message.reply_text("    .")
        return WAITING_AUDIO
    niche = context.user_data.get("niche", "")
    niche_ctx = NICHES_CTX.get(niche, "")
    status = await update.message.reply_text(" !  ...")
    tmp = None
    try:
        with tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False) as f:
            await file.download_to_drive(f.name); tmp = f.name
        with open(tmp, "rb") as af:
            transcript = client.audio.transcriptions.create(model="whisper-large-v3", file=(f"audio.{ext}", af), language="ru", response_format="text")
        if not transcript or len(transcript.strip()) < 30:
            await status.edit_text("   .  .")
            return WAITING_AUDIO
        await status.edit_text(" !    , SPIN  ...")
        prompt = PROMPT.format(niche_context=niche_ctx)
        response = client.chat.completions.create(model="llama-3.3-70b-versatile", max_tokens=4000, messages=[{"role":"system","content":prompt},{"role":"user","content":f"  :\n\n{transcript}"}])
        analysis = response.choices[0].message.content
        await status.delete()
        if len(transcript) < 3000:
            await update.message.reply_text(f":\n\n{transcript[:2900]}")
        text = f"  [{niche}]\n\n{analysis}"
        while text:
            if len(text) <= 4000:
                await update.message.reply_text(text); break
            split = text[:4000].rfind('\n')
            if split == -1: split = 4000
            await update.message.reply_text(text[:split]); text = text[split:].lstrip('\n')
        await update.message.reply_text("   ? !\n /start   .")
    except Exception as e:
        logging.error(f": {e}")
        await update.message.reply_text(f": {str(e)[:200]}")
    finally:
        if tmp:
            try: os.unlink(tmp)
            except: pass
    return WAITING_AUDIO

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("    .\n /start   .\n /help  .")
    return WAITING_AUDIO

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    conv = ConversationHandler(entry_points=[CommandHandler("start", start)], states={CHOOSING_NICHE:[MessageHandler(filters.TEXT & ~filters.COMMAND, choose_niche)], WAITING_AUDIO:[MessageHandler(filters.VOICE | filters.AUDIO, handle_audio), MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text)]}, fallbacks=[CommandHandler("start", start)])
    app.add_handler(conv)
    app.add_handler(CommandHandler("help", help_command))
    print("AI Sales Coach Bot !")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
