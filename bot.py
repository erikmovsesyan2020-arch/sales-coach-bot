import os, logging, tempfile, re
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler, CallbackQueryHandler
from groq import Groq
import pg8000.dbapi
pg8000.dbapi.paramstyle = "format"
from urllib.parse import urlparse

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
client = Groq(api_key=os.environ["GROQ_API_KEY"])
TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
DATABASE_URL = os.environ.get("DATABASE_URL")


def db_connect():
    result = urlparse(DATABASE_URL)
    return pg8000.dbapi.connect(
        user=result.username,
        password=result.password,
        host=result.hostname,
        port=result.port or 5432,
        database=result.path[1:]
    )


def db_init():
    conn = db_connect()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS clients (
            id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            company TEXT,
            contact TEXT,
            direction TEXT,
            sent TEXT,
            next_step TEXT,
            created_date TEXT,
            remind_date TEXT,
            summary TEXT,
            reminded INTEGER DEFAULT 0
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS stats (
            user_id BIGINT PRIMARY KEY,
            calls_count INTEGER DEFAULT 0,
            first_seen TEXT,
            last_seen TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS user_settings (
            user_id BIGINT PRIMARY KEY,
            niche TEXT
        )
    """)
    for col, coltype in [("remind_date", "TEXT"), ("summary", "TEXT"), ("reminded", "INTEGER DEFAULT 0")]:
        try:
            cur.execute(f"ALTER TABLE clients ADD COLUMN IF NOT EXISTS {col} {coltype}")
        except Exception as mig_err:
            logging.error("Migration: " + str(mig_err))
    conn.commit()
    cur.close()
    conn.close()
    logging.info("Database initialized")


def db_set_niche(user_id, niche):
    conn = db_connect()
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM user_settings WHERE user_id = %s", (user_id,))
    if cur.fetchone():
        cur.execute("UPDATE user_settings SET niche = %s WHERE user_id = %s", (niche, user_id))
    else:
        cur.execute("INSERT INTO user_settings (user_id, niche) VALUES (%s, %s)", (user_id, niche))
    conn.commit()
    cur.close()
    conn.close()


def db_get_niche(user_id):
    conn = db_connect()
    cur = conn.cursor()
    cur.execute("SELECT niche FROM user_settings WHERE user_id = %s", (user_id,))
    r = cur.fetchone()
    cur.close()
    conn.close()
    return r[0] if r else None


def db_add_client(user_id, data):
    conn = db_connect()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO clients (user_id, company, contact, direction, sent, next_step, created_date, remind_date, summary, reminded) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 0)",
        (user_id, data['company'], data['contact'], data['direction'], data['sent'], data['next_step'], data['date'], data.get('remind_date', ''), data.get('summary', ''))
    )
    conn.commit()
    cur.close()
    conn.close()


def db_get_due_reminders(today):
    conn = db_connect()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, user_id, company, contact, direction, next_step, summary FROM clients WHERE remind_date = %s AND reminded = 0",
        (today,)
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows


def db_mark_reminded(client_id):
    conn = db_connect()
    cur = conn.cursor()
    cur.execute("UPDATE clients SET reminded = 1 WHERE id = %s", (client_id,))
    conn.commit()
    cur.close()
    conn.close()


def db_get_clients(user_id):
    conn = db_connect()
    cur = conn.cursor()
    cur.execute("SELECT company, contact, direction, sent, next_step, created_date, summary, remind_date, id FROM clients WHERE user_id = %s ORDER BY id DESC", (user_id,))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    result = []
    for r in rows:
        result.append({
            'company': r[0], 'contact': r[1], 'direction': r[2],
            'sent': r[3], 'next_step': r[4], 'created_date': r[5],
            'summary': r[6], 'remind_date': r[7], 'id': r[8]
        })
    return result


def db_get_client_by_id(client_id, user_id):
    conn = db_connect()
    cur = conn.cursor()
    cur.execute("SELECT company, contact, direction, sent, next_step, created_date, summary, remind_date, id FROM clients WHERE id = %s AND user_id = %s", (client_id, user_id))
    r = cur.fetchone()
    cur.close()
    conn.close()
    if not r:
        return None
    return {
        'company': r[0], 'contact': r[1], 'direction': r[2],
        'sent': r[3], 'next_step': r[4], 'created_date': r[5],
        'summary': r[6], 'remind_date': r[7], 'id': r[8]
    }


def db_update_client_field(client_id, user_id, field, value):
    allowed = {'company', 'contact', 'direction', 'sent', 'next_step', 'remind_date'}
    if field not in allowed:
        return False
    conn = db_connect()
    cur = conn.cursor()
    cur.execute(f"UPDATE clients SET {field} = %s WHERE id = %s AND user_id = %s", (value, client_id, user_id))
    conn.commit()
    cur.close()
    conn.close()
    return True


def db_delete_client(client_id, user_id):
    conn = db_connect()
    cur = conn.cursor()
    cur.execute("DELETE FROM clients WHERE id = %s AND user_id = %s", (client_id, user_id))
    conn.commit()
    cur.close()
    conn.close()


def db_track_call(user_id):
    conn = db_connect()
    cur = conn.cursor()
    now = datetime.now().strftime('%d.%m.%Y')
    cur.execute("SELECT user_id FROM stats WHERE user_id = %s", (user_id,))
    if cur.fetchone():
        cur.execute("UPDATE stats SET calls_count = calls_count + 1, last_seen = %s WHERE user_id = %s", (now, user_id))
    else:
        cur.execute("INSERT INTO stats (user_id, calls_count, first_seen, last_seen) VALUES (%s, 1, %s, %s)", (user_id, now, now))
    conn.commit()
    cur.close()
    conn.close()


def db_get_stats():
    conn = db_connect()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM stats")
    total_users = cur.fetchone()[0]
    cur.execute("SELECT COALESCE(SUM(calls_count), 0) FROM stats")
    total_calls = cur.fetchone()[0]
    today = datetime.now().strftime('%d.%m.%Y')
    cur.execute("SELECT COUNT(*) FROM stats WHERE last_seen = %s", (today,))
    active_today = cur.fetchone()[0]
    cur.close()
    conn.close()
    return total_users, total_calls, active_today


CHOOSING_NICHE, WAITING_AUDIO, WAITING_COMPANY, WAITING_CONTACT, WAITING_FROM, WAITING_FROM_CUSTOM, WAITING_TO, WAITING_TO_CUSTOM, WAITING_SENT, WAITING_NEXT_STEP, WAITING_REMIND = range(11)

RU_MONTHS = ['', '\u042f\u043d\u0432\u0430\u0440\u044c', '\u0424\u0435\u0432\u0440\u0430\u043b\u044c', '\u041c\u0430\u0440\u0442', '\u0410\u043f\u0440\u0435\u043b\u044c', '\u041c\u0430\u0439', '\u0418\u044e\u043d\u044c', '\u0418\u044e\u043b\u044c', '\u0410\u0432\u0433\u0443\u0441\u0442', '\u0421\u0435\u043d\u0442\u044f\u0431\u0440\u044c', '\u041e\u043a\u0442\u044f\u0431\u0440\u044c', '\u041d\u043e\u044f\u0431\u0440\u044c', '\u0414\u0435\u043a\u0430\u0431\u0440\u044c']

PORTS_FROM = ['\u0428\u0430\u043d\u0445\u0430\u0439', '\u0426\u0438\u043d\u0434\u0430\u043e', '\u041d\u0438\u043d\u0433\u0431\u043e', '\u0413\u0443\u0430\u043d\u0447\u0436\u043e\u0443', '\u0428\u044d\u043d\u044c\u0447\u0436\u044d\u043d\u044c', '\u0414\u0440\u0443\u0433\u043e\u0435']
CITIES_TO = ['\u041c\u043e\u0441\u043a\u0432\u0430', '\u0421\u0430\u043d\u043a\u0442-\u041f\u0435\u0442\u0435\u0440\u0431\u0443\u0440\u0433', '\u041d\u043e\u0432\u043e\u0440\u043e\u0441\u0441\u0438\u0439\u0441\u043a', '\u0412\u043b\u0430\u0434\u0438\u0432\u043e\u0441\u0442\u043e\u043a', '\u0415\u043a\u0430\u0442\u0435\u0440\u0438\u043d\u0431\u0443\u0440\u0433', '\u0414\u0440\u0443\u0433\u043e\u0435']

NICHES = ['\u041b\u043e\u0433\u0438\u0441\u0442\u0438\u043a\u0430']
NICHES_CTX = {'\u041b\u043e\u0433\u0438\u0441\u0442\u0438\u043a\u0430': '\u041d\u0438\u0448\u0430: \u0433\u0440\u0443\u0437\u043e\u043f\u0435\u0440\u0435\u0432\u043e\u0437\u043a\u0438 \u0438 \u043b\u043e\u0433\u0438\u0441\u0442\u0438\u043a\u0430. \u041c\u0430\u0440\u0448\u0440\u0443\u0442\u044b, \u0441\u0440\u043e\u043a\u0438, \u0444\u0440\u0430\u0445\u0442, \u043e\u0431\u044a\u0435\u043c\u044b, \u0442\u0438\u043f\u044b \u043a\u043e\u043d\u0442\u0435\u0439\u043d\u0435\u0440\u043e\u0432.'}

WHISPER_PROMPT = "\u0417\u0432\u043e\u043d\u043e\u043a \u043f\u043e \u043c\u0435\u0436\u0434\u0443\u043d\u0430\u0440\u043e\u0434\u043d\u043e\u0439 \u043b\u043e\u0433\u0438\u0441\u0442\u0438\u043a\u0435. \u0422\u0435\u0440\u043c\u0438\u043d\u044b: \u0426\u0438\u043d\u0434\u0430\u043e, \u0428\u0430\u043d\u0445\u0430\u0439, \u0413\u0443\u0430\u043d\u0447\u0436\u043e\u0443, \u041d\u0438\u043d\u0433\u0431\u043e, \u0422\u044f\u043d\u0446\u0437\u0438\u043d, \u0412\u043b\u0430\u0434\u0438\u0432\u043e\u0441\u0442\u043e\u043a, \u041d\u043e\u0432\u043e\u0440\u043e\u0441\u0441\u0438\u0439\u0441\u043a, \u041c\u043e\u0441\u043a\u0432\u0430, 20-\u0444\u0443\u0442\u043e\u0432\u044b\u0439, 40-\u0444\u0443\u0442\u043e\u0432\u044b\u0439, \u043a\u043e\u043d\u0442\u0435\u0439\u043d\u0435\u0440, FCL, LCL, TEU, \u0444\u0440\u0430\u0445\u0442, \u0442\u0430\u043c\u043e\u0436\u043d\u044f, \u043a\u043e\u043d\u043e\u0441\u0430\u043c\u0435\u043d\u0442, \u043f\u0435\u0440\u0435\u0432\u043e\u0437\u0447\u0438\u043a, \u043b\u043e\u0433\u0438\u0441\u0442\u0438\u043a\u0430, \u0434\u043e\u0441\u0442\u0430\u0432\u043a\u0430, \u0433\u0440\u0443\u0437, \u0438\u043c\u043f\u043e\u0440\u0442, \u044d\u043a\u0441\u043f\u043e\u0440\u0442, \u0441\u0442\u0430\u0432\u043a\u0430, \u0440\u0430\u0441\u0447\u0435\u0442."

PROMPT = (
    "\u0422\u044b - AI Sales Coach, \u044d\u043a\u0441\u043f\u0435\u0440\u0442 \u043f\u043e \u043f\u0440\u043e\u0434\u0430\u0436\u0430\u043c \u043c\u0438\u0440\u043e\u0432\u043e\u0433\u043e \u0443\u0440\u043e\u0432\u043d\u044f \u0432 B2B, \u0441\u043f\u0435\u0446\u0438\u0430\u043b\u0438\u0437\u0430\u0446\u0438\u044f - \u043b\u043e\u0433\u0438\u0441\u0442\u0438\u043a\u0430 \u0438 \u0433\u0440\u0443\u0437\u043e\u043f\u0435\u0440\u0435\u0432\u043e\u0437\u043a\u0438.\n\n"
    "IMPORTANT: \u041e\u0442\u0432\u0435\u0447\u0430\u0439 \u0422\u041e\u041b\u042c\u041a\u041e \u043d\u0430 \u0440\u0443\u0441\u0441\u043a\u043e\u043c \u044f\u0437\u044b\u043a\u0435. \u041d\u0418\u041a\u041e\u0413\u0414\u0410 \u043d\u0435 \u0438\u0441\u043f\u043e\u043b\u044c\u0437\u0443\u0439 \u0441\u0438\u043c\u0432\u043e\u043b\u044b \u0434\u0440\u0443\u0433\u0438\u0445 \u044f\u0437\u044b\u043a\u043e\u0432 (\u043a\u0438\u0442\u0430\u0439\u0441\u043a\u0438\u0435, \u0430\u0440\u0430\u0431\u0441\u043a\u0438\u0435 \u0438 \u0442\u0434). \u0422\u043e\u043b\u044c\u043a\u043e \u0440\u0443\u0441\u0441\u043a\u0438\u0439 \u0442\u0435\u043a\u0441\u0442.\n\n"
    "{niche_context}\n\n"
    "\u041c\u0415\u0422\u041e\u0414\u041e\u041b\u041e\u0413\u0418\u042f: Jordan Belfort (\u0422\u0440\u0438 \u0434\u0435\u0441\u044f\u0442\u043a\u0438 \u0443\u0432\u0435\u0440\u0435\u043d\u043d\u043e\u0441\u0442\u0438), SPIN Selling, \u0421\u0435\u0440\u0433\u0435\u0439 \u0424\u0438\u043b\u0438\u043f\u043f\u043e\u0432 Sales 3.0, \u042d\u0440\u0438\u043a \u041c\u043e\u0432\u0441\u0435\u0441\u044f\u043d.\n\n"
    "\u0411\u0410\u0417\u041e\u0412\u042b\u0415 \u041f\u0420\u0418\u041d\u0426\u0418\u041f\u042b:\n"
    "- \u0423\u043b\u044b\u0431\u043a\u0430 \u0438 \u044d\u043c\u043e\u0446\u0438\u043e\u043d\u0430\u043b\u044c\u043d\u0430\u044f \u044d\u043d\u0435\u0440\u0433\u0438\u044f \u0447\u0443\u0432\u0441\u0442\u0432\u0443\u044e\u0442\u0441\u044f \u0434\u0430\u0436\u0435 \u043f\u043e \u0442\u0435\u043b\u0435\u0444\u043e\u043d\u0443 - \u044d\u0442\u043e \u0444\u0443\u043d\u0434\u0430\u043c\u0435\u043d\u0442\n"
    "- \u0413\u041b\u0410\u0412\u041d\u0410\u042f \u0426\u0415\u041b\u042c \u0437\u0432\u043e\u043d\u043a\u0430 \u0432 \u043b\u043e\u0433\u0438\u0441\u0442\u0438\u043a\u0435 = \u043f\u043e\u043b\u0443\u0447\u0438\u0442\u044c \u0417\u0410\u041f\u0420\u041e\u0421 (\u043d\u0430\u043f\u0440\u0430\u0432\u043b\u0435\u043d\u0438\u0435, \u0442\u0438\u043f \u043a\u043e\u043d\u0442\u0435\u0439\u043d\u0435\u0440\u0430, \u0442\u0438\u043f \u0433\u0440\u0443\u0437\u0430)\n"
    "- \u0421\u043d\u0430\u0447\u0430\u043b\u0430 \u043f\u0440\u043e\u0434\u0430\u0439 \u0441\u0435\u0431\u044f, \u043f\u043e\u0442\u043e\u043c \u043a\u043e\u043c\u043f\u0430\u043d\u0438\u044e, \u043f\u043e\u0442\u043e\u043c \u0443\u0441\u043b\u0443\u0433\u0443 (\u0424\u0438\u043b\u0438\u043f\u043f\u043e\u0432)\n"
    "\u0428\u041a\u0410\u041b\u0410 \u041e\u0426\u0415\u041d\u041a\u0418 (\u0431\u0443\u0434\u044c \u0447\u0435\u0441\u0442\u043d\u044b\u043c \u0438 \u0441\u043f\u0440\u0430\u0432\u0435\u0434\u043b\u0438\u0432\u044b\u043c):\n"
    "9-10: \u043f\u043e\u043b\u0443\u0447\u0438\u043b \u043f\u043e\u043b\u043d\u044b\u0439 \u0437\u0430\u043f\u0440\u043e\u0441 + \u043e\u0442\u043b\u0438\u0447\u043d\u043e \u043e\u0442\u0440\u0430\u0431\u043e\u0442\u0430\u043b \u0432\u043e\u0437\u0440\u0430\u0436\u0435\u043d\u0438\u044f + \u0443\u0441\u0442\u0430\u043d\u043e\u0432\u0438\u043b \u043a\u043e\u043d\u0442\u0430\u043a\u0442\n"
    "7-8: \u043f\u043e\u043b\u0443\u0447\u0438\u043b \u0437\u0430\u043f\u0440\u043e\u0441 (\u043d\u0430\u043f\u0440\u0430\u0432\u043b\u0435\u043d\u0438\u0435+\u043a\u043e\u043d\u0442\u0435\u0439\u043d\u0435\u0440+\u0433\u0440\u0443\u0437) + \u043e\u0431\u0440\u0430\u0431\u043e\u0442\u0430\u043b \u0432\u043e\u0437\u0440\u0430\u0436\u0435\u043d\u0438\u044f\n"
    "5-6: \u043f\u043e\u043b\u0443\u0447\u0438\u043b \u0447\u0430\u0441\u0442\u044c \u0437\u0430\u043f\u0440\u043e\u0441\u0430 \u0438\u043b\u0438 \u043d\u0435 \u043e\u0442\u0440\u0430\u0431\u043e\u0442\u0430\u043b \u0432\u043e\u0437\u0440\u0430\u0436\u0435\u043d\u0438\u044f\n"
    "3-4: \u043d\u0435 \u043f\u043e\u043b\u0443\u0447\u0438\u043b \u0437\u0430\u043f\u0440\u043e\u0441, \u043f\u043e\u0442\u0435\u0440\u044f\u043b \u043a\u043b\u0438\u0435\u043d\u0442\u0430\n"
    "1-2: \u043f\u043e\u043b\u043d\u044b\u0439 \u043f\u0440\u043e\u0432\u0430\u043b\n"
    "\u0412\u0410\u0416\u041d\u041e: \u0435\u0441\u043b\u0438 \u043f\u0440\u043e\u0434\u0430\u0436\u043d\u0438\u043a \u043f\u043e\u043b\u0443\u0447\u0438\u043b \u0437\u0430\u043f\u0440\u043e\u0441 - \u044d\u0442\u043e \u0443\u0441\u043f\u0435\u0445! \u041d\u0435 \u0437\u0430\u043d\u0438\u0436\u0430\u0439 \u043e\u0446\u0435\u043d\u043a\u0443 \u0435\u0441\u043b\u0438 \u0446\u0435\u043b\u044c \u0434\u043e\u0441\u0442\u0438\u0433\u043d\u0443\u0442\u0430.\n\n"
    "\u0428\u0410\u0413 1 - \u041e\u041f\u0420\u0415\u0414\u0415\u041b\u0418 \u041a\u0422\u041e \u0415\u0421\u0422\u042c \u041a\u0422\u041e\n\n"
    "\u0412\u043d\u0438\u043c\u0430\u0442\u0435\u043b\u044c\u043d\u043e \u043f\u0440\u043e\u0447\u0438\u0442\u0430\u0439 \u0442\u0440\u0430\u043d\u0441\u043a\u0440\u0438\u043f\u0446\u0438\u044e. \u041e\u043f\u0440\u0435\u0434\u0435\u043b\u0438 \u0440\u043e\u043b\u0438 \u043f\u043e \u043a\u043e\u043d\u0442\u0435\u043a\u0441\u0442\u0443:\n"
    "\u041f\u0420\u041e\u0414\u0410\u0416\u041d\u0418\u041a: \u0433\u043e\u0432\u043e\u0440\u0438\u0442 \u043f\u0435\u0440\u0432\u044b\u043c, \u0434\u043b\u0438\u043d\u043d\u044b\u0435 \u0444\u0440\u0430\u0437\u044b, \u043f\u0440\u0435\u0434\u043b\u0430\u0433\u0430\u0435\u0442, \u0437\u0430\u0434\u0430\u0435\u0442 \u0432\u043e\u043f\u0440\u043e\u0441\u044b, \u0440\u0430\u0431\u043e\u0442\u0430\u0435\u0442 \u0441 \u0432\u043e\u0437\u0440\u0430\u0436\u0435\u043d\u0438\u044f\u043c\u0438\n"
    "\u041a\u041b\u0418\u0415\u041d\u0422: \u043a\u043e\u0440\u043e\u0442\u043a\u0438\u0435 \u043e\u0442\u0432\u0435\u0442\u044b, \u0443\u043a\u043b\u043e\u043d\u044f\u0435\u0442\u0441\u044f, \u0432\u043e\u0437\u0440\u0430\u0436\u0430\u0435\u0442, \u0433\u043e\u0432\u043e\u0440\u0438\u0442 \u00ab\u043f\u043e\u0434\u0443\u043c\u0430\u044e\u00bb\n\n"
    "\u0428\u0410\u0413 2 - \u041f\u041e\u041b\u041d\u042b\u0419 \u0410\u041d\u0410\u041b\u0418\u0417\n\n"
    "\u041e\u0426\u0415\u041d\u041a\u0410 \u0417\u0412\u041e\u041d\u041a\u0410: [X/10]\n"
    "[\u041e\u0434\u043d\u043e \u043f\u0440\u0435\u0434\u043b\u043e\u0436\u0435\u043d\u0438\u0435-\u0432\u0435\u0440\u0434\u0438\u043a\u0442]\n\n"
    "\u041a\u0422\u041e \u0415\u0421\u0422\u042c \u041a\u0422\u041e\n"
    "\u041f\u0440\u043e\u0434\u0430\u0436\u043d\u0438\u043a: [\u043a\u0430\u043a \u043e\u043f\u0440\u0435\u0434\u0435\u043b\u0438\u043b, \u0438\u043c\u044f]\n"
    "\u041a\u043b\u0438\u0435\u043d\u0442: [\u043a\u0430\u043a \u043e\u043f\u0440\u0435\u0434\u0435\u043b\u0438\u043b, \u043a\u043e\u043c\u043f\u0430\u043d\u0438\u044f \u0435\u0441\u043b\u0438 \u0443\u043f\u043e\u043c\u044f\u043d\u0443\u0442\u0430]\n"
    "\u042d\u043c\u043e\u0446\u0438\u0438: [\u0442\u043e\u043d \u043f\u0440\u043e\u0434\u0430\u0436\u043d\u0438\u043a\u0430 + \u0442\u043e\u043d \u043a\u043b\u0438\u0435\u043d\u0442\u0430]\n\n"
    "\u0420\u0410\u0417\u0411\u041e\u0420 \u041f\u041e \u041a\u0420\u0418\u0422\u0415\u0420\u0418\u042f\u041c\n\n"
    "1. \u042d\u041c\u041e\u0426\u0418\u041e\u041d\u0410\u041b\u042c\u041d\u042b\u0419 \u0417\u0410\u0425\u0412\u0410\u0422 [X/10]\n"
    "\u0421\u043e\u0437\u0434\u0430\u043b \u043b\u0438 \u043f\u0440\u043e\u0434\u0430\u0436\u043d\u0438\u043a \u044d\u043c\u043e\u0446\u0438\u043e\u043d\u0430\u043b\u044c\u043d\u044b\u0439 \u043a\u043e\u043d\u0442\u0430\u043a\u0442 \u0432 \u043f\u0435\u0440\u0432\u044b\u0435 \u0441\u0435\u043a\u0443\u043d\u0434\u044b?\n"
    "\u0425\u043e\u0440\u043e\u0448\u043e: [\u043a\u043e\u043d\u043a\u0440\u0435\u0442\u043d\u043e]\n"
    "\u0423\u043f\u0443\u0449\u0435\u043d\u043e: [\u043a\u043e\u043d\u043a\u0440\u0435\u0442\u043d\u043e]\n"
    "\u0420\u0435\u043a\u043e\u043c\u0435\u043d\u0434\u0430\u0446\u0438\u044f: [\u043a\u043e\u043d\u043a\u0440\u0435\u0442\u043d\u0430\u044f \u0444\u0440\u0430\u0437\u0430]\n\n"
    "2. \u041f\u041e\u041b\u0423\u0427\u0415\u041d\u0418\u0415 \u0417\u0410\u041f\u0420\u041e\u0421\u0410 [X/10]\n"
    "\u0413\u041b\u0410\u0412\u041d\u0410\u042f \u0426\u0415\u041b\u042c: \u043d\u0430\u043f\u0440\u0430\u0432\u043b\u0435\u043d\u0438\u0435 + \u0442\u0438\u043f \u043a\u043e\u043d\u0442\u0435\u0439\u043d\u0435\u0440\u0430 + \u0442\u0438\u043f \u0433\u0440\u0443\u0437\u0430\n"
    "\u041f\u043e\u043b\u0443\u0447\u0435\u043d\u043e: [\u0447\u0442\u043e \u0443\u0437\u043d\u0430\u043b]\n"
    "\u041d\u0435 \u043f\u043e\u043b\u0443\u0447\u0435\u043d\u043e: [\u0447\u0442\u043e \u043d\u0435 \u0443\u0437\u043d\u0430\u043b]\n\n"
    "3. \u0412\u042b\u042f\u0412\u041b\u0415\u041d\u0418\u0415 \u041f\u041e\u0422\u0420\u0415\u0411\u041d\u041e\u0421\u0422\u0415\u0419 [X/10]\n"
    "\u0425\u043e\u0440\u043e\u0448\u043e: [\u043a\u043e\u043d\u043a\u0440\u0435\u0442\u043d\u043e]\n"
    "\u0423\u043f\u0443\u0449\u0435\u043d\u043e: [\u043a\u043e\u043d\u043a\u0440\u0435\u0442\u043d\u043e]\n"
    "\u0421\u043e\u0432\u0435\u0442 SPIN: [\u043a\u043e\u043d\u043a\u0440\u0435\u0442\u043d\u044b\u0439 \u0432\u043e\u043f\u0440\u043e\u0441]\n\n"
    "4. \u0420\u0410\u0411\u041e\u0422\u0410 \u0421 \u0412\u041e\u0417\u0420\u0410\u0416\u0415\u041d\u0418\u042f\u041c\u0418 [X/10]\n"
    "\u0425\u043e\u0440\u043e\u0448\u043e: [\u043a\u043e\u043d\u043a\u0440\u0435\u0442\u043d\u043e]\n"
    "\u0423\u043f\u0443\u0449\u0435\u043d\u043e: [\u043a\u043e\u043d\u043a\u0440\u0435\u0442\u043d\u043e]\n"
    "\u041b\u0443\u0447\u0448\u0438\u0439 \u043e\u0442\u0432\u0435\u0442: [\u043a\u043e\u043d\u043a\u0440\u0435\u0442\u043d\u0430\u044f \u0444\u0440\u0430\u0437\u0430]\n\n"
    "5. \u0423\u0412\u0415\u0420\u0415\u041d\u041d\u041e\u0421\u0422\u042c \u0418 \u0422\u041e\u041d [X/10]\n"
    "\u0425\u043e\u0440\u043e\u0448\u043e: [\u043a\u043e\u043d\u043a\u0440\u0435\u0442\u043d\u043e]\n"
    "\u0423\u043f\u0443\u0449\u0435\u043d\u043e: [\u043a\u043e\u043d\u043a\u0440\u0435\u0442\u043d\u043e]\n\n"
    "6. \u0421\u0422\u0420\u0423\u041a\u0422\u0423\u0420\u0410 \u041f\u0420\u041e\u0414\u0410\u0416\u0418 [X/10]\n"
    "\u0425\u043e\u0440\u043e\u0448\u043e: [\u043a\u043e\u043d\u043a\u0440\u0435\u0442\u043d\u043e]\n"
    "\u0423\u043f\u0443\u0449\u0435\u043d\u043e: [\u043a\u043e\u043d\u043a\u0440\u0435\u0442\u043d\u043e]\n\n"
    "7. \u0418\u041d\u0418\u0426\u0418\u0410\u0422\u0418\u0412\u0410 \u0418 \u0414\u041e\u0416\u0418\u041c [X/10]\n"
    "\u0425\u043e\u0440\u043e\u0448\u043e: [\u043a\u043e\u043d\u043a\u0440\u0435\u0442\u043d\u043e]\n"
    "\u0423\u043f\u0443\u0449\u0435\u043d\u043e: [\u043a\u043e\u043d\u043a\u0440\u0435\u0442\u043d\u043e]\n\n"
    "8. \u0421\u0418\u0413\u041d\u0410\u041b\u042b \u041a\u041b\u0418\u0415\u041d\u0422\u0410 [X/10]\n"
    "\u0425\u043e\u0440\u043e\u0448\u043e: [\u043a\u043e\u043d\u043a\u0440\u0435\u0442\u043d\u043e]\n"
    "\u0423\u043f\u0443\u0449\u0435\u043d\u043e: [\u043a\u043e\u043d\u043a\u0440\u0435\u0442\u043d\u043e]\n\n"
    "\u0422\u041e\u041f-3 \u041e\u0428\u0418\u0411\u041a\u0418\n\n"
    "\u041e\u0448\u0438\u0431\u043a\u0430 1: \"[\u0446\u0438\u0442\u0430\u0442\u0430]\"\n"
    "\u041f\u043e\u0447\u0435\u043c\u0443 \u043f\u043b\u043e\u0445\u043e: [\u043e\u0431\u044a\u044f\u0441\u043d\u0435\u043d\u0438\u0435]\n"
    "\u041a\u0430\u043a \u043d\u0430\u0434\u043e \u0431\u044b\u043b\u043e: \"[\u0444\u0440\u0430\u0437\u0430]\"\n\n"
    "\u041e\u0448\u0438\u0431\u043a\u0430 2: \"[\u0446\u0438\u0442\u0430\u0442\u0430]\"\n"
    "\u041f\u043e\u0447\u0435\u043c\u0443 \u043f\u043b\u043e\u0445\u043e: [\u043e\u0431\u044a\u044f\u0441\u043d\u0435\u043d\u0438\u0435]\n"
    "\u041a\u0430\u043a \u043d\u0430\u0434\u043e \u0431\u044b\u043b\u043e: \"[\u0444\u0440\u0430\u0437\u0430]\"\n\n"
    "\u041e\u0448\u0438\u0431\u043a\u0430 3: \"[\u0446\u0438\u0442\u0430\u0442\u0430]\"\n"
    "\u041f\u043e\u0447\u0435\u043c\u0443 \u043f\u043b\u043e\u0445\u043e: [\u043e\u0431\u044a\u044f\u0441\u043d\u0435\u043d\u0438\u0435]\n"
    "\u041a\u0430\u043a \u043d\u0430\u0434\u043e \u0431\u044b\u043b\u043e: \"[\u0444\u0440\u0430\u0437\u0430]\"\n\n"
    "3 \u0428\u0410\u0413\u0410 \u0414\u041b\u042f \u0420\u041e\u0421\u0422\u0410\n"
    "1. [\u0434\u0435\u0439\u0441\u0442\u0432\u0438\u0435 + \u043f\u0440\u0438\u043c\u0435\u0440 \u0444\u0440\u0430\u0437\u044b]\n"
    "2. [\u0434\u0435\u0439\u0441\u0442\u0432\u0438\u0435 + \u043f\u0440\u0438\u043c\u0435\u0440 \u0444\u0440\u0430\u0437\u044b]\n"
    "3. [\u0434\u0435\u0439\u0441\u0442\u0432\u0438\u0435 + \u043f\u0440\u0438\u043c\u0435\u0440 \u0444\u0440\u0430\u0437\u044b]\n\n"
    "\u0418\u0422\u041e\u0413\n"
    "\u0421\u0438\u043b\u0430 \u043c\u0435\u043d\u0435\u0434\u0436\u0435\u0440\u0430: [\u043a\u043e\u043d\u043a\u0440\u0435\u0442\u043d\u043e]\n"
    "\u0413\u043b\u0430\u0432\u043d\u044b\u0439 \u0444\u043e\u043a\u0443\u0441: [\u041e\u0414\u041d\u041e \u0434\u0435\u0439\u0441\u0442\u0432\u0438\u0435]\n"
    "\u0426\u0435\u043b\u044c \u043d\u0430 \u0441\u043b\u0435\u0434\u0443\u044e\u0449\u0438\u0439 \u0437\u0432\u043e\u043d\u043e\u043a: [\u043a\u043e\u043d\u043a\u0440\u0435\u0442\u043d\u044b\u0439 \u0440\u0435\u0437\u0443\u043b\u044c\u0442\u0430\u0442]\n"
)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    kb = [[n] for n in NICHES]
    await update.message.reply_text('\u041f\u0440\u0438\u0432\u0435\u0442! \u042f AI Sales Coach.\n\n\u0412 \u043a\u0430\u043a\u043e\u0439 \u043e\u0431\u043b\u0430\u0441\u0442\u0438 \u0432\u044b \u0440\u0430\u0431\u043e\u0442\u0430\u0435\u0442\u0435?', reply_markup=ReplyKeyboardMarkup(kb, one_time_keyboard=True, resize_keyboard=True))
    return CHOOSING_NICHE


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text('\u0411\u043e\u0442 \u0430\u043d\u0430\u043b\u0438\u0437\u0438\u0440\u0443\u0435\u0442 \u0437\u0430\u043f\u0438\u0441\u0438 \u0437\u0432\u043e\u043d\u043a\u043e\u0432.\n\n\u041f\u043e\u043b\u0443\u0447\u0438\u0448\u044c:\n- \u041e\u0446\u0435\u043d\u043a\u0430 \u043f\u043e 8 \u043a\u0440\u0438\u0442\u0435\u0440\u0438\u044f\u043c\n- \u0420\u0430\u0437\u0431\u043e\u0440 \u043e\u0448\u0438\u0431\u043e\u043a \u0441 \u0446\u0438\u0442\u0430\u0442\u0430\u043c\u0438\n- \u041a\u043e\u043d\u043a\u0440\u0435\u0442\u043d\u044b\u0435 \u0444\u0440\u0430\u0437\u044b \u043a\u0430\u043a \u043d\u0430\u0434\u043e \u0431\u044b\u043b\u043e \u043e\u0442\u0432\u0435\u0442\u0438\u0442\u044c\n- \u041c\u0438\u043d\u0438-CRM: \u0437\u0430\u043f\u0438\u0441\u044c \u043f\u043e \u043a\u043b\u0438\u0435\u043d\u0442\u0443 \u043f\u043e\u0441\u043b\u0435 \u0437\u0432\u043e\u043d\u043a\u0430\n\n\u041a\u043e\u043c\u0430\u043d\u0434\u044b:\n/crm - \u0441\u043f\u0438\u0441\u043e\u043a \u0432\u0441\u0435\u0445 \u043a\u043b\u0438\u0435\u043d\u0442\u043e\u0432\n/start - \u043d\u0430\u0447\u0430\u0442\u044c \u0437\u0430\u043d\u043e\u0432\u043e\n\n\u041c\u0435\u0442\u043e\u0434\u043e\u043b\u043e\u0433\u0438\u044f: Belfort, SPIN, \u0424\u0438\u043b\u0438\u043f\u043f\u043e\u0432, \u041c\u043e\u0432\u0441\u0435\u0441\u044f\u043d\n\n\u041f\u0440\u043e\u0441\u0442\u043e \u043e\u0442\u043f\u0440\u0430\u0432\u044c \u0430\u0443\u0434\u0438\u043e!')


def format_client_card(c):
    text = f"\U0001f3e2 {c['company']}\n"
    text += f"\U0001f464 {c['contact']}\n"
    text += f"\U0001f4cd {c['direction']}\n"
    text += f"\U0001f4e4 \u041e\u0442\u043f\u0440\u0430\u0432\u043b\u0435\u043d\u043e: {c['sent']}\n"
    text += f"\U0001f4de \u0421\u043b\u0435\u0434. \u0448\u0430\u0433: {c['next_step']}\n"
    if c.get('remind_date'):
        text += f"\U0001f514 \u041d\u0430\u043f\u043e\u043c\u043d\u044e: {c['remind_date']}\n"
    if c.get('summary'):
        text += f"\U0001f4ac {c['summary']}\n"
    text += f"\U0001f4c5 {c['created_date']}"
    return text


def client_buttons(client_id):
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("\u270f\ufe0f \u0418\u0437\u043c\u0435\u043d\u0438\u0442\u044c", callback_data=f"edit_{client_id}"),
        InlineKeyboardButton("\U0001f5d1 \u0423\u0434\u0430\u043b\u0438\u0442\u044c", callback_data=f"del_{client_id}")
    ]])


async def crm_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    clients = db_get_clients(user_id)
    if not clients:
        await update.message.reply_text('\u0423 \u0432\u0430\u0441 \u043f\u043e\u043a\u0430 \u043d\u0435\u0442 \u043a\u043b\u0438\u0435\u043d\u0442\u043e\u0432.\n\n\u041f\u0440\u043e\u0430\u043d\u0430\u043b\u0438\u0437\u0438\u0440\u0443\u0439\u0442\u0435 \u0437\u0432\u043e\u043d\u043e\u043a \u0438 \u0434\u043e\u0431\u0430\u0432\u044c\u0442\u0435 \u043f\u0435\u0440\u0432\u043e\u0433\u043e \u043a\u043b\u0438\u0435\u043d\u0442\u0430!')
        return
    text = f'\U0001f4cb \u0421\u041f\u0418\u0421\u041e\u041a \u041a\u041b\u0418\u0415\u041d\u0422\u041e\u0412 ({len(clients)})\n\n'
    for i, c in enumerate(clients, 1):
        text += f"{i}. {c['company']}\n"
        text += f"   \U0001f464 {c['contact']}\n"
        text += f"   \U0001f4cd {c['direction']}\n"
        text += f"   \U0001f4e4 \u041e\u0442\u043f\u0440\u0430\u0432\u043b\u0435\u043d\u043e: {c['sent']}\n"
        text += f"   \U0001f4de \u0421\u043b\u0435\u0434. \u0448\u0430\u0433: {c['next_step']}\n"
        if c.get('remind_date'):
            text += f"   \U0001f514 \u041d\u0430\u043f\u043e\u043c\u043d\u044e: {c['remind_date']}\n"
        if c.get('summary'):
            text += f"   \U0001f4ac {c['summary']}\n"
        text += f"   \U0001f4c5 {c['created_date']}\n\n"
    text += "\u2702\ufe0f \u0418\u0437\u043c\u0435\u043d\u0438\u0442\u044c \u0438\u043b\u0438 \u0443\u0434\u0430\u043b\u0438\u0442\u044c \u043a\u043b\u0438\u0435\u043d\u0442\u0430: /edit"
    while text:
        if len(text) <= 4000:
            await update.message.reply_text(text)
            break
        split = text[:4000].rfind("\n\n")
        if split == -1:
            split = 4000
        await update.message.reply_text(text[:split])
        text = text[split:].lstrip("\n")


async def edit_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    clients = db_get_clients(user_id)
    if not clients:
        await update.message.reply_text('\u0423 \u0432\u0430\u0441 \u043f\u043e\u043a\u0430 \u043d\u0435\u0442 \u043a\u043b\u0438\u0435\u043d\u0442\u043e\u0432.')
        return
    await update.message.reply_text('\u2702\ufe0f \u0420\u0415\u0414\u0410\u041a\u0422\u0418\u0420\u041e\u0412\u0410\u041d\u0418\u0415\n\u041d\u0430\u0436\u043c\u0438\u0442\u0435 \u043a\u043d\u043e\u043f\u043a\u0443 \u043f\u043e\u0434 \u043d\u0443\u0436\u043d\u044b\u043c \u043a\u043b\u0438\u0435\u043d\u0442\u043e\u043c:')
    for c in clients:
        await update.message.reply_text(format_client_card(c), reply_markup=client_buttons(c['id']))


ADMIN_ID = 1437708144


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != ADMIN_ID:
        return
    total_users, total_calls, active_today = db_get_stats()
    text = (
        "\U0001f4ca \u0421\u0422\u0410\u0422\u0418\u0421\u0422\u0418\u041a\u0410 \u0411\u041e\u0422\u0410\n\n"
        f"\U0001f465 \u0412\u0441\u0435\u0433\u043e \u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u0435\u0439: {total_users}\n"
        f"\U0001f4de \u0412\u0441\u0435\u0433\u043e \u0437\u0432\u043e\u043d\u043a\u043e\u0432: {total_calls}\n"
        f"\U0001f7e2 \u0410\u043a\u0442\u0438\u0432\u043d\u044b \u0441\u0435\u0433\u043e\u0434\u043d\u044f: {active_today}"
    )
    await update.message.reply_text(text)


async def choose_niche(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    niche = update.message.text
    if niche not in NICHES:
        kb = [[n] for n in NICHES]
        await update.message.reply_text('\u0412\u044b\u0431\u0435\u0440\u0438 \u043e\u0431\u043b\u0430\u0441\u0442\u044c \u0438\u0437 \u0441\u043f\u0438\u0441\u043a\u0430', reply_markup=ReplyKeyboardMarkup(kb, one_time_keyboard=True, resize_keyboard=True))
        return CHOOSING_NICHE
    context.user_data["niche"] = niche
    db_set_niche(update.effective_user.id, niche)
    await update.message.reply_text('\u041e\u0442\u043b\u0438\u0447\u043d\u043e! \u041d\u0438\u0448\u0430: ' + niche + '\n\n\u041e\u0442\u043f\u0440\u0430\u0432\u044c \u0437\u0430\u043f\u0438\u0441\u044c \u0437\u0432\u043e\u043d\u043a\u0430.\n\n\u041d\u0443\u0436\u043d\u0430 \u043f\u043e\u043c\u043e\u0449\u044c? /help', reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END


async def handle_audio(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.voice:
        file = await update.message.voice.get_file()
        ext = "ogg"
    elif update.message.audio:
        file = await update.message.audio.get_file()
        ext = "mp3"
    else:
        await update.message.reply_text('\u041e\u0442\u043f\u0440\u0430\u0432\u044c \u0430\u0443\u0434\u0438\u043e\u0444\u0430\u0439\u043b \u0438\u043b\u0438 \u0433\u043e\u043b\u043e\u0441\u043e\u0432\u043e\u0435 \u0441\u043e\u043e\u0431\u0449\u0435\u043d\u0438\u0435.')
        return WAITING_AUDIO
    niche = context.user_data.get("niche")
    if not niche:
        niche = db_get_niche(update.effective_user.id) or '\u041b\u043e\u0433\u0438\u0441\u0442\u0438\u043a\u0430'
        context.user_data["niche"] = niche
    niche_ctx = NICHES_CTX.get(niche, "")
    status = await update.message.reply_text('\u041f\u043e\u043b\u0443\u0447\u0438\u043b \u0437\u0430\u043f\u0438\u0441\u044c! \u0422\u0440\u0430\u043d\u0441\u043a\u0440\u0438\u0431\u0438\u0440\u0443\u044e...')
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
                response_format="text",
                prompt=WHISPER_PROMPT
            )
        if not transcript or len(transcript.strip()) < 30:
            await status.edit_text('\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u0440\u0430\u0441\u043f\u043e\u0437\u043d\u0430\u0442\u044c \u0440\u0435\u0447\u044c. \u041f\u043e\u043f\u0440\u043e\u0431\u0443\u0439 \u0441\u043d\u043e\u0432\u0430.')
            return WAITING_AUDIO
        await status.edit_text('\u0422\u0435\u043a\u0441\u0442 \u0433\u043e\u0442\u043e\u0432! \u0410\u043d\u0430\u043b\u0438\u0437\u0438\u0440\u0443\u044e...')
        prompt = PROMPT.format(niche_context=niche_ctx)
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            max_tokens=4000,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": '\u041f\u0440\u043e\u0430\u043d\u0430\u043b\u0438\u0437\u0438\u0440\u0443\u0439 \u0437\u0432\u043e\u043d\u043e\u043a:\n\n' + str(transcript)}
            ]
        )
        analysis = response.choices[0].message.content
        try:
            db_track_call(update.effective_user.id)
        except Exception as track_err:
            logging.error("Track error: " + str(track_err))
        # \u0413\u0435\u043d\u0435\u0440\u0438\u0440\u0443\u0435\u043c \u0441\u0443\u0442\u044c \u0440\u0430\u0437\u0433\u043e\u0432\u043e\u0440\u0430 \u0434\u043b\u044f \u043d\u0430\u043f\u043e\u043c\u0438\u043d\u0430\u043d\u0438\u044f
        try:
            summary_resp = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                temperature=0.3,
                max_tokens=120,
                messages=[
                    {"role": "system", "content": "\u0422\u044b \u043f\u043e\u043c\u043e\u0449\u043d\u0438\u043a. \u041d\u0430\u043f\u0438\u0448\u0438 \u0421\u0423\u0422\u042c \u0437\u0432\u043e\u043d\u043a\u0430 \u041e\u0414\u041d\u0418\u041c \u043a\u043e\u0440\u043e\u0442\u043a\u0438\u043c \u043f\u0440\u0435\u0434\u043b\u043e\u0436\u0435\u043d\u0438\u0435\u043c (\u0434\u043e 15 \u0441\u043b\u043e\u0432), \u0447\u0442\u043e\u0431\u044b \u043f\u0440\u043e\u0434\u0430\u0432\u0435\u0446 \u0432\u0441\u043f\u043e\u043c\u043d\u0438\u043b \u043a\u043b\u0438\u0435\u043d\u0442\u0430. \u0411\u0435\u0437 \u0432\u0441\u0442\u0443\u043f\u043b\u0435\u043d\u0438\u0439, \u0442\u043e\u043b\u044c\u043a\u043e \u0441\u0443\u0442\u044c. \u041f\u0440\u0438\u043c\u0435\u0440: '\u0417\u0430\u043f\u0440\u043e\u0441\u0438\u043b \u0441\u0442\u0430\u0432\u043a\u0443 \u0428\u0430\u043d\u0445\u0430\u0439-\u041c\u043e\u0441\u043a\u0432\u0430, \u0435\u0441\u0442\u044c \u0441\u0432\u043e\u0438 \u043f\u0435\u0440\u0435\u0432\u043e\u0437\u0447\u0438\u043a\u0438, \u0433\u043e\u0442\u043e\u0432 \u0441\u0440\u0430\u0432\u043d\u0438\u0442\u044c'"},
                    {"role": "user", "content": str(transcript)}
                ]
            )
            summary_text = summary_resp.choices[0].message.content.strip()
            summary_text = re.sub(r'[\u1100-\u11FF\u2E80-\u2FFF\u3040-\u9FFF\uA000-\uA4FF\uAC00-\uD7FF\uF900-\uFAFF]', '', summary_text)
            context.user_data['crm_summary'] = summary_text
        except Exception as sum_err:
            logging.error("Summary error: " + str(sum_err))
            context.user_data['crm_summary'] = ''
        analysis = re.sub(r'[\u1100-\u11FF\u2E80-\u2FFF\u3040-\u9FFF\uA000-\uA4FF\uAC00-\uD7FF\uF900-\uFAFF]', '', analysis)
        analysis = analysis.replace("\u0425\u043e\u0440\u043e\u0448\u043e:", "\U0001f7e2 \u0425\u043e\u0440\u043e\u0448\u043e:")
        analysis = analysis.replace("\u0423\u043f\u0443\u0449\u0435\u043d\u043e:", "\U0001f534 \u0423\u043f\u0443\u0449\u0435\u043d\u043e:")
        analysis = analysis.replace("\u0417\u0430\u043c\u0435\u0447\u0435\u043d\u043e:", "\U0001f7e2 \u0417\u0430\u043c\u0435\u0447\u0435\u043d\u043e:")
        analysis = analysis.replace("\u041d\u0435 \u043f\u043e\u043b\u0443\u0447\u0435\u043d\u043e:", "\U0001f534 \u041d\u0435 \u043f\u043e\u043b\u0443\u0447\u0435\u043d\u043e:")
        analysis = analysis.replace("\u041f\u043e\u043b\u0443\u0447\u0435\u043d\u043e:", "\U0001f7e2 \u041f\u043e\u043b\u0443\u0447\u0435\u043d\u043e:")
        analysis = analysis.replace("\u0427\u0442\u043e \u0441\u0440\u0430\u0431\u043e\u0442\u0430\u043b\u043e:", "\U0001f7e2 \u0427\u0442\u043e \u0441\u0440\u0430\u0431\u043e\u0442\u0430\u043b\u043e:")
        analysis = analysis.replace("\u0427\u0442\u043e \u0443\u043f\u0443\u0449\u0435\u043d\u043e:", "\U0001f534 \u0427\u0442\u043e \u0443\u043f\u0443\u0449\u0435\u043d\u043e:")
        analysis = analysis.replace("\u0417\u0435\u043b\u0435\u043d\u044b\u0439 \u043a\u0440\u0443\u0433:", "\U0001f7e2")
        analysis = analysis.replace("\u041a\u0440\u0430\u0441\u043d\u044b\u0439 \u043a\u0440\u0443\u0433:", "\U0001f534")
        analysis = analysis.replace("*", "")
        analysis = analysis.replace("\u041a\u0422\u041e \u0415\u0421\u0422\u042c \u041a\u0422\u041e", "\u0423\u0427\u0410\u0421\u0422\u041d\u0418\u041a\u0418 \u0417\u0412\u041e\u041d\u041a\u0410")
        await status.delete()
        if len(str(transcript)) < 3000:
            await update.message.reply_text('\u0422\u0420\u0410\u041d\u0421\u041a\u0420\u0418\u041f\u0426\u0418\u042f:\n\n' + str(transcript)[:2900])
        text = '\u0410\u041d\u0410\u041b\u0418\u0417 \u0417\u0412\u041e\u041d\u041a\u0410 [' + niche + "]\n\n" + analysis
        while text:
            if len(text) <= 4000:
                await update.message.reply_text(text)
                break
            split = text[:4000].rfind("\n")
            if split == -1:
                split = 4000
            await update.message.reply_text(text[:split])
            text = text[split:].lstrip("\n")

        context.user_data['last_transcript'] = str(transcript)
        await update.message.reply_text(
            '\u0414\u043e\u0431\u0430\u0432\u0438\u0442\u044c \u043a\u043b\u0438\u0435\u043d\u0442\u0430 \u0432 CRM?\n\u041d\u0430\u043f\u0438\u0448\u0438 \u043d\u0430\u0437\u0432\u0430\u043d\u0438\u0435 \u043a\u043e\u043c\u043f\u0430\u043d\u0438\u0438 \u0438\u043b\u0438 \u043d\u0430\u0436\u043c\u0438 \u041f\u0440\u043e\u043f\u0443\u0441\u0442\u0438\u0442\u044c:',
            reply_markup=ReplyKeyboardMarkup([['\u041f\u0440\u043e\u043f\u0443\u0441\u0442\u0438\u0442\u044c']], one_time_keyboard=True, resize_keyboard=True)
        )
        return WAITING_COMPANY

    except Exception as e:
        logging.error("Error: " + str(e))
        await update.message.reply_text('\u041e\u0448\u0438\u0431\u043a\u0430: ' + str(e)[:200])
    finally:
        if tmp:
            try:
                os.unlink(tmp)
            except Exception:
                pass
    return WAITING_AUDIO


async def waiting_company(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text
    if text == '\u041f\u0440\u043e\u043f\u0443\u0441\u0442\u0438\u0442\u044c':
        await update.message.reply_text('\u041e\u043a! \u041e\u0442\u043f\u0440\u0430\u0432\u044c \u0441\u043b\u0435\u0434\u0443\u044e\u0449\u0438\u0439 \u0437\u0432\u043e\u043d\u043e\u043a.', reply_markup=ReplyKeyboardRemove())
        return WAITING_AUDIO
    context.user_data['crm_company'] = text
    await update.message.reply_text(
        '\u0418\u043c\u044f \u0438 \u0442\u0435\u043b\u0435\u0444\u043e\u043d \u043a\u043e\u043d\u0442\u0430\u043a\u0442\u0430?\n(\u043d\u0430\u043f\u0440\u0438\u043c\u0435\u0440: \u0418\u0432\u0430\u043d \u0418\u0432\u0430\u043d\u043e\u0432, +7 999 123 45 67)',
        reply_markup=ReplyKeyboardMarkup([['\u041f\u0440\u043e\u043f\u0443\u0441\u0442\u0438\u0442\u044c']], one_time_keyboard=True, resize_keyboard=True)
    )
    return WAITING_CONTACT


async def waiting_contact(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text
    context.user_data['crm_contact'] = text if text != '\u041f\u0440\u043e\u043f\u0443\u0441\u0442\u0438\u0442\u044c' else '-'
    kb = [[PORTS_FROM[0], PORTS_FROM[1]], [PORTS_FROM[2], PORTS_FROM[3]], [PORTS_FROM[4], PORTS_FROM[5]]]
    await update.message.reply_text('\u041e\u0442\u043a\u0443\u0434\u0430? (\u043f\u043e\u0440\u0442 \u043e\u0442\u043f\u0440\u0430\u0432\u043b\u0435\u043d\u0438\u044f)', reply_markup=ReplyKeyboardMarkup(kb, one_time_keyboard=True, resize_keyboard=True))
    return WAITING_FROM


async def waiting_from(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text
    if text == '\u0414\u0440\u0443\u0433\u043e\u0435':
        await update.message.reply_text('\u041d\u0430\u043f\u0438\u0448\u0438\u0442\u0435 \u043f\u043e\u0440\u0442 \u043e\u0442\u043f\u0440\u0430\u0432\u043b\u0435\u043d\u0438\u044f:', reply_markup=ReplyKeyboardRemove())
        return WAITING_FROM_CUSTOM
    context.user_data['crm_from'] = text
    kb = [[CITIES_TO[0], CITIES_TO[1]], [CITIES_TO[2], CITIES_TO[3]], [CITIES_TO[4], CITIES_TO[5]]]
    await update.message.reply_text('\u041a\u0443\u0434\u0430? (\u0433\u043e\u0440\u043e\u0434 \u043d\u0430\u0437\u043d\u0430\u0447\u0435\u043d\u0438\u044f)', reply_markup=ReplyKeyboardMarkup(kb, one_time_keyboard=True, resize_keyboard=True))
    return WAITING_TO


async def waiting_from_custom(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['crm_from'] = update.message.text
    kb = [[CITIES_TO[0], CITIES_TO[1]], [CITIES_TO[2], CITIES_TO[3]], [CITIES_TO[4], CITIES_TO[5]]]
    await update.message.reply_text('\u041a\u0443\u0434\u0430? (\u0433\u043e\u0440\u043e\u0434 \u043d\u0430\u0437\u043d\u0430\u0447\u0435\u043d\u0438\u044f)', reply_markup=ReplyKeyboardMarkup(kb, one_time_keyboard=True, resize_keyboard=True))
    return WAITING_TO


async def waiting_to(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text
    if text == '\u0414\u0440\u0443\u0433\u043e\u0435':
        await update.message.reply_text('\u041d\u0430\u043f\u0438\u0448\u0438\u0442\u0435 \u0433\u043e\u0440\u043e\u0434 \u043d\u0430\u0437\u043d\u0430\u0447\u0435\u043d\u0438\u044f:', reply_markup=ReplyKeyboardRemove())
        return WAITING_TO_CUSTOM
    context.user_data['crm_to'] = text
    kb = [['\u041a\u041f', '\u041e\u0431\u0449\u0430\u044f \u0438\u043d\u0444\u043e\u0440\u043c\u0430\u0446\u0438\u044f', '\u041d\u0438\u0447\u0435\u0433\u043e']]
    await update.message.reply_text('\u0427\u0442\u043e \u043e\u0442\u043f\u0440\u0430\u0432\u0438\u043b\u0438 \u043a\u043b\u0438\u0435\u043d\u0442\u0443?', reply_markup=ReplyKeyboardMarkup(kb, one_time_keyboard=True, resize_keyboard=True))
    return WAITING_SENT


async def waiting_to_custom(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['crm_to'] = update.message.text
    kb = [['\u041a\u041f', '\u041e\u0431\u0449\u0430\u044f \u0438\u043d\u0444\u043e\u0440\u043c\u0430\u0446\u0438\u044f', '\u041d\u0438\u0447\u0435\u0433\u043e']]
    await update.message.reply_text('\u0427\u0442\u043e \u043e\u0442\u043f\u0440\u0430\u0432\u0438\u043b\u0438 \u043a\u043b\u0438\u0435\u043d\u0442\u0443?', reply_markup=ReplyKeyboardMarkup(kb, one_time_keyboard=True, resize_keyboard=True))
    return WAITING_SENT


async def waiting_sent(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['crm_sent'] = update.message.text
    kb = [['\u041f\u0435\u0440\u0435\u0437\u0432\u043e\u043d\u0438\u0442\u044c', '\u0416\u0434\u0451\u043c \u043e\u0442\u0432\u0435\u0442\u0430', '\u041e\u0442\u043a\u0430\u0437']]
    await update.message.reply_text('\u0421\u043b\u0435\u0434\u0443\u044e\u0449\u0438\u0439 \u0448\u0430\u0433?', reply_markup=ReplyKeyboardMarkup(kb, one_time_keyboard=True, resize_keyboard=True))
    return WAITING_NEXT_STEP


async def waiting_next_step(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    next_step = update.message.text
    context.user_data['crm_next_step'] = next_step

    # \u0415\u0441\u043b\u0438 \u041e\u0442\u043a\u0430\u0437 - \u0441\u043e\u0445\u0440\u0430\u043d\u044f\u0435\u043c \u0431\u0435\u0437 \u043d\u0430\u043f\u043e\u043c\u0438\u043d\u0430\u043d\u0438\u044f
    if next_step == '\u041e\u0442\u043a\u0430\u0437':
        return await save_client(update, context, remind_date='')

    kb = [['\u0417\u0430\u0432\u0442\u0440\u0430', '\u0427\u0435\u0440\u0435\u0437 3 \u0434\u043d\u044f'], ['\u0412\u044b\u0431\u0440\u0430\u0442\u044c \u0434\u0430\u0442\u0443']]
    await update.message.reply_text('\u041a\u043e\u0433\u0434\u0430 \u043d\u0430\u043f\u043e\u043c\u043d\u0438\u0442\u044c?', reply_markup=ReplyKeyboardMarkup(kb, one_time_keyboard=True, resize_keyboard=True))
    return WAITING_REMIND


def build_calendar(year, month):
    kb = []
    kb.append([InlineKeyboardButton(f"{RU_MONTHS[month]} {year}", callback_data="cal_ignore")])
    days_header = ['\u041f\u043d', '\u0412\u0442', '\u0421\u0440', '\u0427\u0442', '\u041f\u0442', '\u0421\u0431', '\u0412\u0441']
    kb.append([InlineKeyboardButton(d, callback_data="cal_ignore") for d in days_header])
    import calendar as cal_module
    first_weekday, days_in_month = cal_module.monthrange(year, month)
    row = []
    for _ in range(first_weekday):
        row.append(InlineKeyboardButton(" ", callback_data="cal_ignore"))
    for day in range(1, days_in_month + 1):
        row.append(InlineKeyboardButton(str(day), callback_data=f"cal_day_{year}_{month}_{day}"))
        if len(row) == 7:
            kb.append(row)
            row = []
    if row:
        while len(row) < 7:
            row.append(InlineKeyboardButton(" ", callback_data="cal_ignore"))
        kb.append(row)
    prev_m = month - 1 if month > 1 else 12
    prev_y = year if month > 1 else year - 1
    next_m = month + 1 if month < 12 else 1
    next_y = year if month < 12 else year + 1
    kb.append([
        InlineKeyboardButton("\u25c0", callback_data=f"cal_nav_{prev_y}_{prev_m}"),
        InlineKeyboardButton("\u25b6", callback_data=f"cal_nav_{next_y}_{next_m}")
    ])
    return InlineKeyboardMarkup(kb)


async def waiting_remind(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    from datetime import timedelta
    text = update.message.text
    if text == '\u0417\u0430\u0432\u0442\u0440\u0430':
        d = (datetime.now() + timedelta(days=1)).strftime('%d.%m.%Y')
        return await save_client(update, context, remind_date=d)
    if text == '\u0427\u0435\u0440\u0435\u0437 3 \u0434\u043d\u044f':
        d = (datetime.now() + timedelta(days=3)).strftime('%d.%m.%Y')
        return await save_client(update, context, remind_date=d)
    if text == '\u0412\u044b\u0431\u0440\u0430\u0442\u044c \u0434\u0430\u0442\u0443':
        now = datetime.now()
        await update.message.reply_text('\u0412\u044b\u0431\u0435\u0440\u0438\u0442\u0435 \u0434\u0430\u0442\u0443:', reply_markup=ReplyKeyboardRemove())
        await update.message.reply_text('\U0001f4c5', reply_markup=build_calendar(now.year, now.month))
        return WAITING_REMIND
    return WAITING_REMIND


async def calendar_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    data = query.data
    if data == "cal_ignore":
        return WAITING_REMIND
    if data.startswith("cal_nav_"):
        _, _, year, month = data.split("_")
        await query.edit_message_reply_markup(reply_markup=build_calendar(int(year), int(month)))
        return WAITING_REMIND
    if data.startswith("cal_day_"):
        _, _, year, month, day = data.split("_")
        remind_date = f"{int(day):02d}.{int(month):02d}.{year}"
        await query.edit_message_text(f"\U0001f4c5 \u041d\u0430\u043f\u043e\u043c\u043d\u044e: {remind_date}")
        return await save_client(update, context, remind_date=remind_date, via_callback=True)
    return WAITING_REMIND


async def save_client(update, context, remind_date='', via_callback=False):
    if via_callback:
        user_id = update.callback_query.from_user.id
        send = update.callback_query.message.reply_text
    else:
        user_id = update.effective_user.id
        send = update.message.reply_text

    frm = context.user_data.get('crm_from', '-')
    to = context.user_data.get('crm_to', '-')
    direction = frm + ' \u2192 ' + to

    client_data = {
        'company': context.user_data.get('crm_company', '-'),
        'contact': context.user_data.get('crm_contact', '-'),
        'direction': direction,
        'sent': context.user_data.get('crm_sent', '-'),
        'next_step': context.user_data.get('crm_next_step', '-'),
        'date': datetime.now().strftime('%d.%m.%Y'),
        'remind_date': remind_date,
        'summary': context.user_data.get('crm_summary', '')
    }

    db_add_client(user_id, client_data)

    remind_line = f"\n\U0001f514 \u041d\u0430\u043f\u043e\u043c\u043d\u044e: {remind_date}" if remind_date else ""
    summary = context.user_data.get('crm_summary', '')
    summary_line = f"\n\U0001f4ac {summary}" if summary else ""
    card = (
        f"\U0001f4cb \u041a\u043b\u0438\u0435\u043d\u0442 \u0441\u043e\u0445\u0440\u0430\u043d\u0451\u043d!\n\n"
        f"\U0001f3e2 {client_data['company']}\n"
        f"\U0001f464 {client_data['contact']}\n"
        f"\U0001f4cd {client_data['direction']}\n"
        f"\U0001f4e4 \u041e\u0442\u043f\u0440\u0430\u0432\u043b\u0435\u043d\u043e: {client_data['sent']}\n"
        f"\U0001f4de \u0421\u043b\u0435\u0434. \u0448\u0430\u0433: {client_data['next_step']}\n"
        f"\U0001f4c5 {client_data['date']}"
        f"{remind_line}"
        f"{summary_line}"
    )

    await send(card, reply_markup=ReplyKeyboardRemove())
    await send('\u041e\u0442\u043f\u0440\u0430\u0432\u044c \u0441\u043b\u0435\u0434\u0443\u044e\u0449\u0438\u0439 \u0437\u0432\u043e\u043d\u043e\u043a \u0438\u043b\u0438 /crm \u0447\u0442\u043e\u0431\u044b \u0443\u0432\u0438\u0434\u0435\u0442\u044c \u0432\u0441\u0435\u0445 \u043a\u043b\u0438\u0435\u043d\u0442\u043e\u0432.')
    return WAITING_AUDIO


async def check_reminders(context: ContextTypes.DEFAULT_TYPE):
    today = datetime.now().strftime('%d.%m.%Y')
    try:
        due = db_get_due_reminders(today)
    except Exception as e:
        logging.error("Reminders check error: " + str(e))
        return
    for row in due:
        client_id, user_id, company, contact, direction, next_step, summary = row
        summary_line = f"\n\U0001f4ac {summary}" if summary else ""
        text = (
            f"\U0001f514 \u041d\u0430\u043f\u043e\u043c\u0438\u043d\u0430\u043d\u0438\u0435!\n\n"
            f"\U0001f3e2 {company}\n"
            f"\U0001f464 {contact}\n"
            f"\U0001f4cd {direction}\n"
            f"\U0001f4de {next_step}"
            f"{summary_line}"
        )
        try:
            await context.bot.send_message(chat_id=user_id, text=text)
            db_mark_reminded(client_id)
        except Exception as e:
            logging.error("Reminder send error: " + str(e))


EDIT_FIELDS = [
    ("company", "\U0001f3e2 \u041a\u043e\u043c\u043f\u0430\u043d\u0438\u044f"),
    ("contact", "\U0001f464 \u041a\u043e\u043d\u0442\u0430\u043a\u0442"),
    ("direction", "\U0001f4cd \u041d\u0430\u043f\u0440\u0430\u0432\u043b\u0435\u043d\u0438\u0435"),
    ("sent", "\U0001f4e4 \u041e\u0442\u043f\u0440\u0430\u0432\u043b\u0435\u043d\u043e"),
    ("next_step", "\U0001f4de \u0421\u043b\u0435\u0434. \u0448\u0430\u0433"),
    ("remind_date", "\U0001f514 \u041d\u0430\u043f\u043e\u043c\u043d\u0438\u0442\u044c"),
]
FIELD_NAMES = dict(EDIT_FIELDS)


async def crm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id

    # \u0423\u0434\u0430\u043b\u0435\u043d\u0438\u0435 - \u043f\u0435\u0440\u0435\u0441\u043f\u0440\u043e\u0441
    if data.startswith("del_"):
        client_id = int(data[4:])
        c = db_get_client_by_id(client_id, user_id)
        if not c:
            await query.edit_message_text("\u041a\u043b\u0438\u0435\u043d\u0442 \u0443\u0436\u0435 \u0443\u0434\u0430\u043b\u0451\u043d.")
            return
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("\u2705 \u0414\u0430, \u0443\u0434\u0430\u043b\u0438\u0442\u044c", callback_data=f"delyes_{client_id}"),
            InlineKeyboardButton("\u274c \u041d\u0435\u0442", callback_data=f"delno_{client_id}")
        ]])
        await query.edit_message_text(f"\u0423\u0434\u0430\u043b\u0438\u0442\u044c {c['company']}?", reply_markup=kb)
        return

    if data.startswith("delyes_"):
        client_id = int(data[7:])
        db_delete_client(client_id, user_id)
        await query.edit_message_text("\U0001f5d1 \u041a\u043b\u0438\u0435\u043d\u0442 \u0443\u0434\u0430\u043b\u0451\u043d.")
        return

    if data.startswith("delno_"):
        client_id = int(data[6:])
        c = db_get_client_by_id(client_id, user_id)
        if c:
            await query.edit_message_text(format_client_card(c), reply_markup=client_buttons(client_id))
        return

    # \u0420\u0435\u0434\u0430\u043a\u0442\u0438\u0440\u043e\u0432\u0430\u043d\u0438\u0435 - \u0432\u044b\u0431\u043e\u0440 \u043f\u043e\u043b\u044f
    if data.startswith("edit_"):
        client_id = int(data[5:])
        c = db_get_client_by_id(client_id, user_id)
        if not c:
            await query.edit_message_text("\u041a\u043b\u0438\u0435\u043d\u0442 \u0443\u0436\u0435 \u0443\u0434\u0430\u043b\u0451\u043d.")
            return
        rows = []
        for fkey, fname in EDIT_FIELDS:
            rows.append([InlineKeyboardButton(fname, callback_data=f"setf_{client_id}_{fkey}")])
        rows.append([InlineKeyboardButton("\u274c \u041e\u0442\u043c\u0435\u043d\u0430", callback_data=f"delno_{client_id}")])
        await query.edit_message_text(f"\u0427\u0442\u043e \u0438\u0437\u043c\u0435\u043d\u0438\u0442\u044c \u0443 {c['company']}?", reply_markup=InlineKeyboardMarkup(rows))
        return

    # \u0412\u044b\u0431\u0440\u0430\u043b\u0438 \u043f\u043e\u043b\u0435 \u0434\u043b\u044f \u0440\u0435\u0434\u0430\u043a\u0442\u0438\u0440\u043e\u0432\u0430\u043d\u0438\u044f
    if data.startswith("setf_"):
        rest = data[5:]
        client_id_str, fkey = rest.split("_", 1)
        client_id = int(client_id_str)
        context.user_data['editing_client'] = client_id
        context.user_data['editing_field'] = fkey
        cancel_kb = InlineKeyboardMarkup([[InlineKeyboardButton("\u25c0\ufe0f \u041e\u0442\u043c\u0435\u043d\u0430", callback_data=f"canceledit_{client_id}")]])
        await query.edit_message_text(f"\u041d\u0430\u043f\u0438\u0448\u0438\u0442\u0435 \u043d\u043e\u0432\u043e\u0435 \u0437\u043d\u0430\u0447\u0435\u043d\u0438\u0435 \u0434\u043b\u044f \u043f\u043e\u043b\u044f \"{FIELD_NAMES[fkey]}\":", reply_markup=cancel_kb)
        return

    if data.startswith("canceledit_"):
        client_id = int(data[11:])
        context.user_data['editing_client'] = None
        context.user_data['editing_field'] = None
        user_id = query.from_user.id
        c = db_get_client_by_id(client_id, user_id)
        if c:
            await query.edit_message_text(format_client_card(c), reply_markup=client_buttons(client_id))
        else:
            await query.edit_message_text("\u041e\u0442\u043c\u0435\u043d\u0435\u043d\u043e.")
        return


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # \u0415\u0441\u043b\u0438 \u0440\u0435\u0434\u0430\u043a\u0442\u0438\u0440\u0443\u0435\u043c \u043a\u043b\u0438\u0435\u043d\u0442\u0430
    if context.user_data.get('editing_client') and context.user_data.get('editing_field'):
        client_id = context.user_data['editing_client']
        fkey = context.user_data['editing_field']
        user_id = update.effective_user.id
        new_value = update.message.text
        db_update_client_field(client_id, user_id, fkey, new_value)
        context.user_data['editing_client'] = None
        context.user_data['editing_field'] = None
        c = db_get_client_by_id(client_id, user_id)
        await update.message.reply_text("\u2705 \u0418\u0437\u043c\u0435\u043d\u0435\u043d\u043e!")
        if c:
            await update.message.reply_text(format_client_card(c), reply_markup=client_buttons(client_id))
        return WAITING_AUDIO

    await update.message.reply_text('\u041e\u0442\u043f\u0440\u0430\u0432\u044c \u0430\u0443\u0434\u0438\u043e\u0444\u0430\u0439\u043b \u0438\u043b\u0438 \u0433\u043e\u043b\u043e\u0441\u043e\u0432\u043e\u0435.\n\u0418\u043b\u0438 /start \u0447\u0442\u043e\u0431\u044b \u043d\u0430\u0447\u0430\u0442\u044c \u0437\u0430\u043d\u043e\u0432\u043e.\n\u0418\u043b\u0438 /crm \u0447\u0442\u043e\u0431\u044b \u0443\u0432\u0438\u0434\u0435\u0442\u044c \u043a\u043b\u0438\u0435\u043d\u0442\u043e\u0432.')
    return WAITING_AUDIO


def main():
    db_init()
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    conv = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            MessageHandler(filters.VOICE | filters.AUDIO, handle_audio)
        ],
        states={
            CHOOSING_NICHE: [MessageHandler(filters.TEXT & ~filters.COMMAND, choose_niche)],
            WAITING_AUDIO: [
                MessageHandler(filters.VOICE | filters.AUDIO, handle_audio),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text)
            ],
            WAITING_COMPANY: [MessageHandler(filters.TEXT & ~filters.COMMAND, waiting_company)],
            WAITING_CONTACT: [MessageHandler(filters.TEXT & ~filters.COMMAND, waiting_contact)],
            WAITING_FROM: [MessageHandler(filters.TEXT & ~filters.COMMAND, waiting_from)],
            WAITING_FROM_CUSTOM: [MessageHandler(filters.TEXT & ~filters.COMMAND, waiting_from_custom)],
            WAITING_TO: [MessageHandler(filters.TEXT & ~filters.COMMAND, waiting_to)],
            WAITING_TO_CUSTOM: [MessageHandler(filters.TEXT & ~filters.COMMAND, waiting_to_custom)],
            WAITING_SENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, waiting_sent)],
            WAITING_NEXT_STEP: [MessageHandler(filters.TEXT & ~filters.COMMAND, waiting_next_step)],
            WAITING_REMIND: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, waiting_remind),
                CallbackQueryHandler(calendar_callback, pattern="^cal_")
            ],
        },
        fallbacks=[CommandHandler("start", start)]
    )
    app.add_handler(conv)
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("crm", crm_command))
    app.add_handler(CommandHandler("edit", edit_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CallbackQueryHandler(crm_callback, pattern="^(edit_|del_|delyes_|delno_|setf_|canceledit_)"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    job_queue = app.job_queue
    if job_queue:
        job_queue.run_repeating(check_reminders, interval=3600, first=30)

    print("Bot started!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
