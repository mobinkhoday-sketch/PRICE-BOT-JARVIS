# -*- coding: utf-8 -*-
# Telegram price bot (Iran market via Navasan + BTC/USD via Binance)
# Schedules: 11:00, 13:00, 15:00, 17:00 Asia/Tehran

import os
import sqlite3
import requests
from datetime import datetime
from pytz import timezone
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import telebot

# -------------------- تنظیمات --------------------
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")  # از BotFather
if not TELEGRAM_TOKEN:
    raise RuntimeError("متغیر محیطی TELEGRAM_TOKEN تنظیم نشده.")

# کلید API نوسان (طبق درخواست داخل کد ذخیره شد)
NAVASAN_API_KEY = "free9GhrgJaOqGJPHGGwhYSON7WK5jnj"

# دیتابیس محلی برای نگهداری مشترک‌ها
DB_PATH = "bot.db"

# ناحیه زمانی تهران برای زمان‌بندی
TZ = timezone("Asia/Tehran")

# راه‌اندازی ربات
bot = telebot.TeleBot(TELEGRAM_TOKEN, parse_mode="HTML")

# -------------------- دیتابیس --------------------
def init_db():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS subscribers (
            chat_id INTEGER PRIMARY KEY,
            created_at TEXT NOT NULL
        )
    """)
    con.commit()
    con.close()

def add_subscriber(chat_id: int):
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("INSERT OR IGNORE INTO subscribers(chat_id, created_at) VALUES(?, ?)",
                (chat_id, datetime.utcnow().isoformat()))
    con.commit()
    con.close()

def remove_subscriber(chat_id: int):
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("DELETE FROM subscribers WHERE chat_id=?", (chat_id,))
    con.commit()
    con.close()

def list_subscribers():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("SELECT chat_id FROM subscribers")
    rows = [r[0] for r in cur.fetchall()]
    con.close()
    return rows

# -------------------- گرفتن قیمت‌ها --------------------
def fetch_navasan_latest():
    """
    داده‌های آخرین قیمت از نوسان.
    مستندات دقیق کلیدها ممکنه متفاوت باشه؛ این نگاشت رو در صورت نیاز اصلاح کن.
    """
    url = f"https://api.navasan.tech/latest/?api_key={NAVASAN_API_KEY}"
    r = requests.get(url, timeout=15)
    r.raise_for_status()
    return r.json()

def get_iran_prices():
    """
    برمی‌گرداند:
      - دلار آزاد (تومان)
      - طلای 18 عیار (تومان)
    نگاشت کلیدها بر اساس خروجی رایج نوسان تنظیم شده؛
    اگر کلیدها متفاوت بودند، در SYMBOL_MAP اصلاح کن.
    """
    data = fetch_navasan_latest()

    # نگاشت‌های معمول (در صورت تفاوت، با print(data.keys()) کلید درست را پیدا و اینجا اصلاح کن)
    SYMBOL_MAP = {
        "usd": ["usd", "price_dollar_rl", "dollar"],   # یکی از این‌ها در خروجی موجود خواهد بود
        "gold_18": ["geram18", "gold_18", "gerami18"], # طلای ۱۸ عیار
    }

    def pick_value(candidates):
        for key in candidates:
            if key in data:
                # ساختار رایج: {"value": "51200", "last_update": "..."}
                v = data[key]
                if isinstance(v, dict) and "value" in v:
                    return int(str(v["value"]).replace(",", "").strip())
                # یا مستقیم عدد
                try:
                    return int(str(v).replace(",", "").strip())
                except:
                    pass
        return None

    usd_irr = pick_value(SYMBOL_MAP["usd"])
    gold18_irr = pick_value(SYMBOL_MAP["gold_18"])

    return usd_irr, gold18_irr

def get_btc_usd():
    """
    قیمت لحظه‌ای بیت‌کوین به دلار از Binance (BTCUSDT).
    """
    url = "https://api.binance.com/api/v3/ticker/price"
    r = requests.get(url, params={"symbol": "BTCUSDT"}, timeout=15)
    r.raise_for_status()
    data = r.json()
    return float(data["price"])

# -------------------- پیام و ارسال --------------------
def fmt_num(n, unit=""):
    if n is None:
        return "نامشخص"
    if isinstance(n, float):
        s = f"{n:,.2f}"
    else:
        s = f"{n:,}"
    return f"{s} {unit}".strip()

def build_message():
    now_teh = datetime.now(TZ).strftime("%Y-%m-%d %H:%M")
    usd_irr, gold18_irr = None, None
    btc_usd = None
    err = None

    try:
        usd_irr, gold18_irr = get_iran_prices()
    except Exception as e:
        err = f"خطا در دریافت از نوسان: {e}"

    try:
        btc_usd = get_btc_usd()
    except Exception as e:
        err = (err + " | " if err else "") + f"خطا در دریافت BTC از Binance: {e}"

    msg = [f"📊 <b>گزارش قیمت</b> — ⏰ {now_teh} (Asia/Tehran)\n"]
    msg.append(f"💵 دلار آزاد: <b>{fmt_num(usd_irr, 'تومان')}</b>")
    msg.append(f"🥇 طلای ۱۸ عیار: <b>{fmt_num(gold18_irr, 'تومان')}</b>")
    msg.append(f"₿ بیت‌کوین (دلاری): <b>{fmt_num(btc_usd, 'USD')}</b>")

    if err:
        msg.append(f"\n⚠️ {err}")

    return "\n".join(msg)

def send_to_all():
    subs = list_subscribers()
    if not subs:
        return
    text = build_message()
    for chat_id in subs:
        try:
            bot.send_message(chat_id, text)
        except Exception as e:
            # اگر کاربری ربات را بلاک کرده، ادامه بده
            print(f"Failed to send to {chat_id}: {e}")

# -------------------- دستورات تلگرام --------------------
@bot.message_handler(commands=["start"])
def cmd_start(message):
    add_subscriber(message.chat.id)
    bot.reply_to(message, "سلام 👋\nاز این پس در ساعات ۱۱، ۱۳، ۱۵ و ۱۷ به وقت تهران قیمت‌ها برات میاد.\n"
                          "برای لغو: /stop\n"
                          "برای دریافت فوری: /now")
@bot.message_handler(commands=["stop"])
def cmd_stop(message):
    remove_subscriber(message.chat.id)
    bot.reply_to(message, "اشتراک شما لغو شد. برای فعال‌سازی دوباره: /start")

@bot.message_handler(commands=["now"])
def cmd_now(message):
    bot.reply_to(message, build_message())

# -------------------- زمان‌بندی --------------------
def setup_scheduler():
    scheduler = BackgroundScheduler(timezone=TZ)

    # چهار نوبت در روز به وقت تهران: 11:00, 13:00, 15:00, 17:00
    for hour in [11, 13, 15, 17]:
        scheduler.add_job(send_to_all, CronTrigger(hour=hour, minute=0))

    scheduler.start()
    return scheduler

# -------------------- اجرا --------------------
if __name__ == "__main__":
    init_db()
    setup_scheduler()
    print("ربات روشن شد. زمان‌بندی: 11/13/15/17 Asia/Tehran")
    bot.infinity_polling(timeout=60, long_polling_timeout=60)
