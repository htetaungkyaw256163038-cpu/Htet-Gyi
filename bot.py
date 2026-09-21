import os
import json
import asyncio
from datetime import datetime, timezone, timedelta
from telebot.async_telebot import AsyncTeleBot
from telebot.types import Message, Update
from aiohttp import web

# သင့်ရဲ့ Bot Token
BOT_TOKEN = '8851853713:AAE_x4jtZpza4owQ2Bm4d0quQ2BpJ8EWIJk'
RENDER_URL = 'https://htet-gyi.onrender.com'  # သင့် Render URL

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

# ===== Webhook Routes =====
async def handle_webhook(request):
    try:
        body = await request.text()
        update = Update.de_json(body)
        await bot.process_new_updates([update])
    except Exception as e:
        print(f"Webhook error: {e}")
    return web.Response(text="ok")

async def handle_root(request):
    await bot.remove_webhook()
    await bot.set_webhook(url=f"{RENDER_URL}/{BOT_TOKEN}")
    return web.Response(text="webhook set")

async def main():
    print("Bot is running (webhook mode)...")
    
    app = web.Application()
    app.router.add_post(f"/{BOT_TOKEN}", handle_webhook)
    app.router.add_get("/", handle_root)
    
    port = int(os.environ.get("PORT", 10000))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    
    # Render မှာ webhook အလိုအလျောက် သတ်မှတ်
    await bot.remove_webhook()
    await bot.set_webhook(url=f"{RENDER_URL}/{BOT_TOKEN}")
    print(f"Webhook set to {RENDER_URL}/{BOT_TOKEN}")
    
    while True:
        await asyncio.sleep(3600)

if __name__ == '__main__':
    asyncio.run(main())
