import os
import json
import asyncio
from datetime import datetime, timezone, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
from telebot.async_telebot import AsyncTeleBot
from telebot.types import Message

# Render အတွက် Port ဖွင့်ပေးမည့် Dummy Server (Web Service Error မတက်အောင် ကာကွယ်ရန်)
class SimpleHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Telegram Bot is running smoothly!")
    def log_message(self, format, *args):
        pass

def run_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(('0.0.0.0', port), SimpleHandler)
    server.serve_forever()

# Background မှာ Port ဖွင့်ရန် Thread စတင်ခြင်း
server_thread = threading.Thread(target=run_server)
server_thread.daemon = True
server_thread.start()

# သင့်ရဲ့ Bot Token
BOT_TOKEN = '8851853713:AAE_x4jtZpza4owQ2Bm4d0quQ2BpJ8EWIJk'
bot = AsyncTeleBot(BOT_TOKEN)

ADMIN_ID = 2096430319
AUTH_FILE = 'auth_list.json'

def load_auth():
    if not os.path.exists(AUTH_FILE):
        return {}
    try:
        with open(AUTH_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {}

def save_auth(data):
    with open(AUTH_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)

@bot.message_handler(commands=['start'])
async def send_welcome(message: Message):
    await bot.reply_to(message, "Bot စတင်ပါပြီ။ /key ဖြင့်စတင်ပါ။")

@bot.message_handler(commands=['key'])
async def check_key(message: Message):
    user_id = str(message.from_user.id)
    auth_data = load_auth()
    
    if user_id in auth_data:
        info = auth_data[user_id]
        expires_at = datetime.fromisoformat(info['expires_at'])
        if expires_at > datetime.now(timezone.utc):
            await bot.reply_to(message, f"Key မှန်ကန်ပါသည်။ Plan: {info['plan']}")
            return
            
    await bot.reply_to(message, "သင့်ရဲ့ key ကို registered မလုပ်ရသေးပါဘူး။")

@bot.message_handler(commands=['genkey'])
async def generate_key(message: Message):
    if message.from_user.id != ADMIN_ID:
        await bot.reply_to(message, "ဒီ command ကိုသုံးခွင့် မရှိပါ။")
        return
        
    parts = message.text.split()
    if len(parts) < 3:
        await bot.reply_to(message, "ပုံစံမှားနေပါသည်။ ဥပမာ: /genkey 1d 2096430319")
        return
        
    plan = parts[1]
    target_user_id = parts[2]
    
    expires_at = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    if plan == 'unlimited':
        expires_at = "9999-12-31T23:59:59Z"
        
    auth_data = load_auth()
    auth_data[target_user_id] = {
        "expires_at": expires_at,
        "plan": plan
    }
    save_auth(auth_data)
    
    await bot.reply_to(message, f"Key Generated\n\nUSER ID : {target_user_id}\nPLAN : {plan}")

@bot.message_handler(commands=['scan', 'input'])
async def scan_voucher(message: Message):
    user_id = str(message.from_user.id)
    auth_data = load_auth()
    
    if user_id not in auth_data:
        await bot.reply_to(message, "ကျေးဇူးပြု၍ /key ဖြင့် အရင်စစ်ဆေးပါ။")
        return
        
    await bot.reply_to(message, "ဘောက်ချာ စကင်ဖတ်ခြင်း စတင်နေပါပြီ... ကျေးဇူးပြု၍ စောင့်ဆိုင်းပါ။")

async def main():
    print("Bot is running...")
    await bot.infinity_polling()

if __name__ == '__main__':
    asyncio.run(main())
