import os
import json
import asyncio
from datetime import datetime, timezone, timedelta
from telebot.async_telebot import AsyncTeleBot
from telebot.types import Message, Update
import aiohttp
from aiohttp import web
import cv2
import ddddocr
import numpy as np
import base64
import random
import string
import time
import uuid
import concurrent.futures

# ===== သင့်ရဲ့ တိကျတဲ့ Token, URL နဲ့ Admin ID များ =====
BOT_TOKEN = '8851853713:AAE_x4jtZpza4owQ2Bm4d0quQ2BpJ8EWIJk'
RENDER_URL = 'https://htet-gyi.onrender.com'  # သင့် Render URL
GITHUB_TOKEN = ''  # လိုအပ်ပါਕ GitHub Token ထည့်ပါ
REPO_OWNER = "Htet-Gyi"
REPO_NAME = "Htet-Gyi"
ADMIN_ID = 2096430319
# =======================================================

SUCCESS_CODE = asyncio.Queue()
bot = AsyncTeleBot(BOT_TOKEN)
user_data = {}
approve = {}
scan_tasks = {}
success_messages = {}
success_texts = {}
limited_messages = {}
limited_texts = {}
captcha_state = {}
retry_counts = {}
_session_pool = {}

session = None
_connector = None
_voucher_sem = None

_start_time = time.monotonic()

SESSION_POOL_LIMIT = 60
SESSION_POOL_SLOTS = 5
CONCURRENCY = 2500
BATCH_SIZE = 5000

# ===== Webhook & Web Server Routes for Render =====
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
    return web.Response(text="Bot is awake and running 24/7 via Webhook!")

async def rebuild_session():
    global session, _connector
    if session and not session.closed:
        await session.close()
    if _connector and not _connector.closed:
        await _connector.close()
    timeout = aiohttp.ClientTimeout(total=30)
    _connector = aiohttp.TCPConnector(limit=6000, ttl_dns_cache=300, ssl=False)
    session = aiohttp.ClientSession(
        timeout=timeout,
        connector=_connector,
        connector_owner=False
    )

async def get_file_content(path):
    url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/{path}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"} if GITHUB_TOKEN else {}
    if not session:
        return {}, None
    async with session.get(url, headers=headers) as response:
        if response.status == 200:
            data = await response.json()
            content = base64.b64decode(data['content']).decode('utf-8')
            return json.loads(content), data['sha']
    return {}, None

async def update_file_content(path, content, sha, message):
    url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/{path}"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Content-Type": "application/json"
    } if GITHUB_TOKEN else {"Content-Type": "application/json"}
    encoded = base64.b64encode(json.dumps(content).encode()).decode()
    payload = {
        "message": message,
        "content": encoded,
        "sha": sha
    }
    if not session:
        return ""
    async with session.put(url, headers=headers, json=payload) as response:
        return await response.text()

@bot.message_handler(commands=['start'])
async def start(message):
    await bot.reply_to(message, "Bot စတင်ပါပြီ။ /key ဖြင့်စတင်ပါ။")

@bot.message_handler(commands=['key'])
async def handle_key(message):
    global approve
    key = str(message.chat.id)
    auth_list, _ = await get_file_content("auth_list.json")
    if key in auth_list:
        valid = check_key_expiration(auth_list[key])
        if valid:
            approve[message.chat.id] = True
            user_data[message.chat.id] = {}
            await bot.reply_to(
                message,
                "✅ Key မှန်ကန်ပါသည်။ /input ဖြင့် Session URL ထည့်ပါ။"
            )
        else:
            approve[message.chat.id] = False
            await bot.reply_to(
                message,
                "❌ Key Expired ဖြစ်နေပါသည်။"
            )
    else:
        await bot.reply_to(
            message,
            "⚠️ သင်၏ key ကို registered မလုပ်ရသေးပါ။"
        )

@bot.message_handler(commands=['listkeys'])
async def listkeys(message):
    if message.from_user.id != ADMIN_ID:
        await bot.reply_to(message, "No Permission")
        return
    try:
        auth_list, _ = await get_file_content("auth_list.json")
        if not auth_list:
            await bot.reply_to(message, "Registered key မရှိသေးပါ။")
            return
        lines = []
        for uid, data in auth_list.items():
            if isinstance(data, dict):
                expires = data.get("expires_at", "unknown")
                plan = data.get("plan", "unknown")
                if expires == "9999-12-31T23:59:59Z":
                    expires_str = "Unlimited"
                else:
                    try:
                        exp_dt = datetime.fromisoformat(expires.replace("Z", "+00:00"))
                        now = datetime.now(timezone.utc)
                        if exp_dt < now:
                            expires_str = "Expired"
                        else:
                            diff = exp_dt - now
                            days = diff.days
                            hours, rem = divmod(diff.seconds, 3600)
                            minutes = rem // 60
                            expires_str = f"{days}d {hours}h {minutes}m left"
                    except:
                        expires_str = expires
            else:
                plan = "old"
                expires_str = str(data)
            lines.append(f"👤 {uid}\n   Plan: {plan}\n   Expires: {expires_str}")
        text = f"📋 Registered Keys ({len(auth_list)})\n\n" + "\n\n".join(lines)
        if len(text) > 4096:
            for i in range(0, len(text), 4096):
                await bot.send_message(message.chat.id, text[i:i+4096])
        else:
            await bot.reply_to(message, text)
    except Exception as e:
        print(f"Error at listkeys {e}")

@bot.message_handler(commands=['delkey'])
async def delkey(message):
    if message.from_user.id != ADMIN_ID:
        await bot.reply_to(message, "No Permission")
        return
    try:
        args = message.text.split()
        if len(args) < 2:
            await bot.reply_to(message, "Usage:\n/delkey 123456789")
            return
        user_id = args[1]
        auth_list, sha = await get_file_content("auth_list.json")
        if user_id not in auth_list:
            await bot.reply_to(message, f"User ID {user_id} မတွေ့ပါ။")
            return
        del auth_list[user_id]
        await update_file_content(
            "auth_list.json",
            auth_list,
            sha,
            f"Delete key for {user_id}"
        )
        approve.pop(int(user_id), None)
        user_data.pop(int(user_id), None)
        await bot.reply_to(
            message,
            f"🗑️ Key Deleted\n\nUSER ID : {user_id}"
        )
    except Exception as e:
        print(f"Error at delkey {e}")

@bot.message_handler(commands=['genkey'])
async def genkey(message):
    if message.from_user.id != ADMIN_ID:
        await bot.reply_to(message, "No Permission")
        return
    try:
        args = message.text.split()
        if len(args) < 3:
            await bot.reply_to(message, "Usage:\n/genkey 1h 123456789")
            return
        plan = args[1]
        user_id = args[2]
        expiry = generate_expiry(plan)
        if not expiry:
            await bot.reply_to(
                message,
                "Plans:\n30m\n1h\n1d\n7d\n1m\n1y\nunlimited"
            )
            return
        auth_list, sha = await get_file_content("auth_list.json")
        auth_list[user_id] = {
            "expires_at": expiry,
            "plan": plan
        }
        await update_file_content(
            "auth_list.json",
            auth_list,
            sha,
            f"Add key for {user_id}"
        )
        await bot.reply_to(
            message,
            f"🔑 Key Generated\n\n"
            f"USER ID : {user_id}\n"
            f"PLAN : {plan}\n"
            f"EXPIRES : {expiry}"
        )
    except Exception as e:
        print(f"Error at genkey {e}")

@bot.message_handler(commands=['result'])
async def handle_result(message):
    auth_list, _ = await get_file_content("auth_list.json")
    if str(message.chat.id) in auth_list:
        results, _ = await get_file_content("result.json")
        chat_id_str = str(message.chat.id)
        if chat_id_str in results and results[chat_id_str]:
            codes = "\n".join(results[chat_id_str])
            await bot.reply_to(message, f"✅ Found Codes:\n{codes}")
        else:
            await bot.reply_to(message, "သင့်တွင် ယခင်ကရရှိထားသော code မရှိသေးပါ။")
    else:
        await bot.reply_to(message, "သင်၏ key ကို registered မပြုလုပ်ရသေးပါ။")

def check_key_expiration(expiration_time):
    try:
        if isinstance(expiration_time, dict):
            expiry = expiration_time.get("expires_at")
            if expiry == "9999-12-31T23:59:59Z":
                return True
            exp_time = datetime.fromisoformat(
                expiry.replace("Z", "+00:00")
            )
            return datetime.now(timezone.utc) < exp_time
        return False
    except Exception as e:
        print("Key parse error:", e)
        return False

def generate_expiry(plan):
    now = datetime.now(timezone.utc)
    plans = {
        "30m": timedelta(minutes=30),
        "1h": timedelta(hours=1),
        "1d": timedelta(days=1),
        "7d": timedelta(days=7),
        "1m": timedelta(days=30),
        "1y": timedelta(days=365),
        "unlimited": None
    }
    if plan not in plans:
        return None
    if plan == "unlimited":
        return "9999-12-31T23:59:59Z"
    return (now + plans[plan]).isoformat()

@bot.message_handler(commands=['input'])
async def handle_input(message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await bot.reply_to(
            message,
            "Usage:\n\n/input your_session_url"
        )
        return
    url = args[1]
    if message.chat.id in user_data or True:
        user_data.setdefault(message.chat.id, {})
        user_data[message.chat.id]['session_url'] = url
        await bot.reply_to(message, "✅ Session URL အားသိမ်းဆည်းပြီးပါပြီ။ /scan ဖြင့် စတင်ပါ။")

@bot.message_handler(commands=['scan'])
async def scan(message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await bot.reply_to(
            message,
            "Usage:\n\n/scan <6, 7, 8, ascii-lower, all>"
        )
        return
    mode = args[1]
    chat_id = message.chat.id
    if not approve.get(chat_id, False):
        await bot.reply_to(message, "/scan ကိုအသုံးမပြုမီ /key ကိုအရင်ပြုလုပ်ပေးပါ။")
        return
    if chat_id not in user_data or 'session_url' not in user_data[chat_id]:
        await bot.reply_to(message, "/scan ကိုအသုံးမပြုမီ /input ဖြင့် Session URL ကိုအရင်ထည့်သွင်းပေးရပါမည်။")
        return

    progress_msg = await bot.send_message(chat_id, "🔍 Scanning Codes...\n\n")
    await bot.reply_to(message, f"စကင်ဖတ်ခြင်း မုဒ် ({mode}) စတင်နေပါပြီ...")

@bot.message_handler(commands=['status'])
async def status(message):
    if message.from_user.id != ADMIN_ID:
        await bot.reply_to(message, "No Permission")
        return
    active_scans = sum(1 for data in scan_tasks.values() if not data["task"].done()) if scan_tasks else 0
    approved_users = sum(1 for v in approve.values() if v)
    uptime_seconds = int(time.monotonic() - _start_time)
    hours, remainder = divmod(uptime_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    await bot.reply_to(
        message,
        f"📊 Bot Status\n\n"
        f"⏱ Uptime: {hours}h {minutes}m {seconds}s\n"
        f"🔍 Active Scans: {active_scans}\n"
        f"✅ Approved Users: {approved_users}\n"
        f"👥 Sessions Loaded: {len(user_data)}"
    )

async def main():
    await rebuild_session()
    
    app = web.Application()
    app.router.add_post(f"/{BOT_TOKEN}", handle_webhook)
    app.router.add_get("/", handle_root)
    
    port = int(os.environ.get("PORT", 10000))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    
    # Render မှာ Webhook ကို အလိုအလျောက် သတ်မှတ်ပေးခြင်း
    await bot.remove_webhook()
    await bot.set_webhook(url=f"{RENDER_URL}/{BOT_TOKEN}")
    print(f"Bot is running in Webhook mode on port {port}...")
    print(f"Webhook set to {RENDER_URL}/{BOT_TOKEN}")
    
    while True:
        await asyncio.sleep(3600)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    finally:
        if session and not session.closed:
            asyncio.run(session.close())
