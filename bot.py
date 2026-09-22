import os
import telebot
from flask import Flask, request

# Telegram Bot Token သတ်မှတ်ခြင်း
TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN")
bot = telebot.TeleBot(TOKEN)

app = Flask(__name__)

# Render မှ ပေးထားသော သင့် App ရဲ့ Public URL
RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL", "https://your-app-name.onrender.com")
PORT = int(os.environ.get("PORT", 10000))

@app.route(f"/{TOKEN}", methods=["POST"])
def receive_message():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return "!", 200
    else:
        return "Invalid!", 403

@app.route('/')
def index():
    return "Bot Webhook Server is running!"

@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, "မင်္ဂလာပါ! Webhook စနစ်ဖြင့် Bot အလုပ်လုပ်နေပါပြီ။")

@bot.message_handler(commands=['key'])
def check_key(message):
    bot.reply_to(message, "🟢 Proxy Status: ON (Key အချက်အလက်များ အသင့်ရှိပါပြီ)")

@bot.message_handler(commands=['portal'])
def handle_portal(message):
    bot.reply_to(message, "Portal URL လက်ခံရရှိပါပြီ။ ကျေးဇူးပြု၍ VOUCHER Mode (6, 7, 8) ကို ရွေးချယ်ပါ။")

@bot.message_handler(func=lambda message: message.text in ['6', '7', '8', 'Mode 6', 'Mode 7', 'Mode 8'])
def handle_mode(message):
    mode = message.text.replace('Mode ', '')
    bot.reply_to(message, f"Voucher Mode {mode} ကို ရွေးချယ်ပြီးပါပြီ။ စကန်ဖတ်ခြင်း စတင်နေပါပြီ... 🟢")

if __name__ == "__main__":
    # ပထမဦးစွာ ယခင် Webhook များကို ဖျက်ပြီး အသစ်ပြန်ချိတ်ခြင်း
    bot.remove_webhook()
    bot.set_webhook(url=f"{RENDER_EXTERNAL_URL}/{TOKEN}")
    
    # Flask ဆာဗာကို စတင်ခြင်း
    app.run(host="0.0.0.0", port=PORT)
