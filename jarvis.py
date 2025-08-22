import os
import requests
import telebot
from apscheduler.schedulers.background import BackgroundScheduler
import pytz
from datetime import datetime

# گرفتن توکن‌ها
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
NAVA_API_KEY = os.getenv("NAVA_API_KEY")

bot = telebot.TeleBot(TELEGRAM_TOKEN)

# منطقه زمانی تهران
tehran_tz = pytz.timezone("Asia/Tehran")

# لیست یوزرها
subscribers = set()

# گرفتن قیمت دلار و طلا از نوسان
def get_navasan_price(symbol):
    url = f"https://api.navasan.tech/latest/{symbol}?api_key={NAVA_API_KEY}"
    try:
        res = requests.get(url, timeout=10)
        res.raise_for_status()
        data = res.json()
        return data["value"]
    except Exception as e:
        return f"خطا در دریافت {symbol}: {e}"

# گرفتن قیمت بیت کوین از CoinGecko
def get_bitcoin_price():
    url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd"
    try:
        res = requests.get(url, timeout=10)
        res.raise_for_status()
        data = res.json()
        return data["bitcoin"]["usd"]
    except Exception as e:
        return f"خطا در دریافت BTC: {e}"

# ساخت پیام
def build_message():
    dollar = get_navasan_price("usd_rl")
    gold = get_navasan_price("geram18")
    bitcoin = get_bitcoin_price()
    now = datetime.now(tehran_tz).strftime("%Y-%m-%d %H:%M")

    return (
        f"📊 قیمت‌ها در {now}\n\n"
        f"💵 دلار: {dollar}\n"
        f"🥇 طلا ۱۸ عیار: {gold}\n"
        f"₿ بیت‌کوین (USD): {bitcoin}\n"
    )

# ارسال برای همه
def send_prices():
    message = build_message()
    for chat_id in subscribers:
        try:
            bot.send_message(chat_id, message)
        except Exception as e:
            print(f"خطا در ارسال به {chat_id}: {e}")

# فرمان /start
@bot.message_handler(commands=['start'])
def start(message):
    chat_id = message.chat.id
    subscribers.add(chat_id)
    bot.reply_to(message, "✅ شما عضو شدید! از این به بعد قیمت‌ها سر ساعت براتون ارسال میشه.")
    # همون لحظه هم قیمت بفرسته
    bot.send_message(chat_id, build_message())

# زمان‌بندی
scheduler = BackgroundScheduler(timezone=tehran_tz)
for h in [11, 13, 15, 17]:
    scheduler.add_job(send_prices, 'cron', hour=h, minute=0)
scheduler.start()

print("Jarvis bot started...")
bot.infinity_polling()
