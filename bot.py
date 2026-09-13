import os
import sys

# =============================================================
# Render CPU ပေါ်တွင် ONNX Runtime / GPU Error မတက်စေရန် 
# အခြား Packages များ Import မလုပ်မီ အပေါ်ဆုံးမှ အတင်းအကြပ် CPU ပြောင်းလဲခိုင်းခြင်း
# =============================================================
os.environ["ONNXRUNTIME_PROVIDERS"] = "CPUExecutionProvider"

import telebot
import asyncio
import aiohttp
import json
import base64
import random
import re
import string
import time
import uuid
import concurrent.futures
from telebot.async_telebot import AsyncTeleBot
from aiohttp import web
import cv2
import ddddocr
import numpy as np
from datetime import datetime, timedelta, timezone

# Render Environment Variables မှ Token ကို လုံခြုံစွာ လှမ်းဖတ်ရန် ပြင်ဆင်ထားပါသည်
BOT_TOKEN = os.environ.get('BOT_TOKEN', '8982068568:AAGBCcp-pRufITLAE0KdQ3p-rkiminTbYtQ')
GITHUB_TOKEN = ''
REPO_OWNER = ""
REPO_NAME = ""
ADMIN_ID = ""
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

# =============================================================
# KEY EXPIRATION & GENERATION FUNCTIONS (သက်တမ်းစစ်ဆေးသည့်အပိုင်း)
# =============================================================
def generate_expiry(plan: str) -> str:
    """ Plan အလိုက် ကုန်ဆုံးမည့် အချိန်ကို ISO format ဖြင့် ထုတ်ပေးရန် """
    now = datetime.now(timezone.utc)
    plan = plan.lower().strip()
    
    if plan == "30m":
        expire_dt = now + timedelta(minutes=30)
    elif plan == "1h":
        expire_dt = now + timedelta(hours=1)
    elif plan == "1d":
        expire_dt = now + timedelta(days=1)
    elif plan == "7d":
        expire_dt = now + timedelta(days=7)
    elif plan == "1m":
        expire_dt = now + timedelta(days=30)  # 1 လကို ရက် 30 ဟု သတ်မှတ်
    elif plan == "1y":
        expire_dt = now + timedelta(days=365)
    elif plan == "unlimited":
        return "9999-12-31T23:59:59Z"
    else:
        return ""  # သတ်မှတ်ချက် မမှန်ကန်လျှင် ဘာမှမပြန်ပါ
        
    return expire_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

def check_key_expiration(user_entry) -> bool:
    """ Key သက်တမ်း ကျန်ရှိသေးခြင်း ရှိ/မရှိ စစ်ဆေးရန် """
    if not isinstance(user_entry, dict):
        try:
            if user_entry == "9999-12-31T23:59:59Z" or user_entry.lower() == "unlimited":
                return True
            exp_dt = datetime.fromisoformat(user_entry.replace("Z", "+00:00"))
            return datetime.now(timezone.utc) < exp_dt
        except:
            return False
            
    expires_at = user_entry.get("expires_at", "")
    if expires_at == "9999-12-31T23:59:59Z":
        return True
        
    try:
        expire_dt = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        return datetime.now(timezone.utc) < expire_dt
    except Exception as e:
        print(f"Error checking expiration: {e}")
        return False

# =============================================================
# RENDER WEB SERVER FUNCTIONS (Render Web Service အသက်ရှင်စေရန်)
# =============================================================
async def handle(request):
    return web.Response(text="Bot is awake and running 24/7!")

async def web_server():
    app = web.Application()
    app.router.add_get('/', handle)
    runner = web.AppRunner(app)
    await runner.setup()
    # Render သည် ၎င်းတို့၏ PORT ကို Environment Variable မှတစ်ဆင့် ပေးလေ့ရှိသည်
    port = int(os.environ.get('PORT', 8099))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    print(f"Web server started on port {port}")

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

async def _drain_stdout(proc, idx):
    if proc and proc.stdout:
        try:
            async for _ in proc.stdout:
                pass
        except Exception:
            pass

async def get_file_content(path):
    url = f"https://github.com{REPO_OWNER}/{REPO_NAME}/contents/{path}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    async with session.get(url, headers=headers) as response:
        if response.status == 200:
            data = await response.json()
            content = base64.b64decode(data['content']).decode('utf-8')
            return json.loads(content), data['sha']
    return {}, None

async def update_file_content(path, content, sha, message):
    url = f"https://github.com{REPO_OWNER}/{REPO_NAME}/contents/{path}"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Content-Type": "application/json"
    }
    encoded = base64.b64encode(json.dumps(content).encode()).decode()
    payload = {
        "message": message,
        "content": encoded,
        "sha": sha
    }
    async with session.put(url, headers=headers, json=payload) as response:
        return await response.text()

# =============================================================
# TELEGRAM BOT HANDLERS (Command များ ကိုင်တွယ်သည့်အပိုင်း)
# =============================================================
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
                " Key မှန်ကန်ပါသည်။ /input ဖြင့် Session URL ထည့်ပါ။"
            )
        else:
            approve[message.chat.id] = False
            await bot.reply_to(
                message,
                " Key Expired ဖြစ်နေပါသည်။"
            )
    else:
        await bot.reply_to(
            message,
            " သင်၏ key ကို registered မလုပ်ရသေးပါ။"
        )

@bot.message_handler(commands=['listkeys'])
async def listkeys(message):
    if str(message.chat.id) != ADMIN_ID:
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
            lines.append(f" {uid}\n   Plan: {plan}\n   Expires: {expires_str}")
        text = f" Registered Keys ({len(auth_list)})\n\n" + "\n\n".join(lines)
        if len(text) > 4096:
            for i in range(0, len(text), 4096):
                await bot.send_message(message.chat.id, text[i:i+4096])
        else:
            await bot.reply_to(message, text)
    except Exception as e:
        print(f"Error at listkeys {e}")

@bot.message_handler(commands=['delkey'])
async def delkey(message):
    if str(message.chat.id) != ADMIN_ID:
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
            f" Key Deleted\n\nUSER ID : {user_id}"
        )
    except Exception as e:
        print(f"Error at delkey {e}")

@bot.message_handler(commands=['genkey'])
async def genkey(message):
    if str(message.chat.id) != ADMIN_ID:
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
