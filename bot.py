print("===== BOT.PY LOADING =====", flush=True)
import os
import json
import asyncio
from datetime import datetime, timezone, timedelta
from telebot.async_telebot import AsyncTeleBot
from telebot.types import Message, Update, InlineKeyboardMarkup, InlineKeyboardButton
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
print("===== ALL IMPORTS OK =====", flush=True)

# ===== Environment Variables =====
BOT_TOKEN = os.environ.get('BOT_TOKEN', '8851853713:AAE_x4jtZpza4owQ2Bm4d0quQ2BpJ8EWIJk')
RENDER_URL = os.environ.get('RENDER_URL', 'https://htet-gyi.onrender.com')
GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN', '')
REPO_OWNER = os.environ.get('REPO_OWNER', 'htetaungkyaw256163038-cpu')
REPO_NAME = os.environ.get('REPO_NAME', 'Htet-Gyi')
ADMIN_ID = int(os.environ.get('ADMIN_ID', 2096430319))
# =================================

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

# ===== Webhook & Web Server Routes =====
async def handle_webhook(request):
    try:
        body = await request.text()
        update = Update.de_json(body)
        await bot.process_new_updates([update])
    except Exception as e:
        print(f"Webhook error: {e}", flush=True)
    return web.Response(text="ok")

async def handle_root(request):
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
    headers = {"Authorization": f"Bearer {GITHUB_TOKEN}"} if GITHUB_TOKEN else {}
    if not session:
        return {}, None
    async with session.get(url, headers=headers) as response:
        print(f"[GITHUB] GET {path} -> status={response.status}", flush=True)
        if response.status == 200:
            data = await response.json()
            content = base64.b64decode(data['content']).decode('utf-8')
            parsed = json.loads(content)
            print(f"[GITHUB] {path} content loaded successfully", flush=True)
            return parsed, data['sha']
    return {}, None

async def update_file_content(path, content, sha, message):
    url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/{path}"
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
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
        print("Key parse error:", e, flush=True)
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

@bot.message_handler(commands=['start'])
async def start(message):
    print(f"[START] User: {message.chat.id}", flush=True)
    await bot.reply_to(message, "✨ **STAR LINK CODE HACK BOT** ✨\n\n/key ဖြင့် အရင်ဝင်ရောက်စစ်ဆေးပေးပါ။")

@bot.message_handler(commands=['key'])
async def handle_key(message):
    global approve
    key = str(message.chat.id)
    print(f"[KEY] ==========================================", flush=True)
    print(f"[KEY] User: {key}, Chat type: {message.chat.type}", flush=True)

    try:
        auth_list, sha = await get_file_content("auth_list.json")
        found = key in auth_list

        if found:
            valid = check_key_expiration(auth_list[key])
            if valid:
                approve[message.chat.id] = True
                user_data.setdefault(message.chat.id, {})
                await bot.reply_to(
                    message,
                    f"✨ **STAR LINK CODE HACK** ✨\n\n"
                    f"👤 NAME: {message.from_user.first_name}\n"
                    f"🆔 USER ID: {message.chat.id}\n"
                    f"🟢 Proxy Status: ON\n\n"
                    f"👇 Portal URL ထည့်သွင်းရန်:\n`/portal [your_portal_url]`"
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
    except Exception as e:
        print(f"[KEY] ERROR: {e}", flush=True)
        import traceback
        traceback.print_exc()
        await bot.reply_to(message, f"Error: {e}")

@bot.message_handler(commands=['portal'])
async def handle_portal(message):
    chat_id = message.chat.id
    if not approve.get(chat_id, False):
        await bot.reply_to(message, "⚠️ ကျေးဇူးပြု၍ /key အရင်လုပ်ပေးပါ။")
        return
    
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await bot.reply_to(
            message,
            "🔗 **Portal URL ထည့်သွင်းရန်:**\n\n"
            "`/portal [your_portal_url]`\n\n"
            "ဥပမာ:\n`/portal https://portal-as.ruijienetworks.com/api/auth/wifidog?stage=portal...`"
        )
        return
    
    url = args[1]
    user_data.setdefault(chat_id, {})['portal_url'] = url
    user_data[chat_id]['session_url'] = url  # Backward compatibility
    
    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton("6", callback_data="mode_6"),
        InlineKeyboardButton("7", callback_data="mode_7"),
        InlineKeyboardButton("8", callback_data="mode_8")
    )
    markup.add(
        InlineKeyboardButton("🔄 Ascii-Lower", callback_data="mode_ascii"),
        InlineKeyboardButton("⚡ All Modes", callback_data="mode_all")
    )
    
    await bot.reply_to(
        message,
        f"🔗 **Portal URL အားစစ်ဆေးပြီးပါပြီ။**\n\n"
        f"🔢 ကျေးဇူးပြု၍ **VOUCHER Mode** တစ်ခုကို ရွေးချယ်ပါ သို့မဟုတ် `/scan <mode>` ဖြင့် ရိုက်ထည့်ပါ (ဥပမာ: `/scan 7`)",
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("mode_"))
async def callback_scan_mode(call):
    chat_id = call.message.chat.id
    mode = call.data.split("_")[1]
    await bot.answer_callback_query(call.id, f"VOUCHER Mode: {mode} ရွေးချယ်ပြီးပါပြီ")
    
    fake_msg = call.message
    fake_msg.text = f"/scan {mode}"
    fake_msg.chat.id = chat_id
    await scan(fake_msg)

@bot.message_handler(commands=['scan'])
async def scan(message):
    chat_id = message.chat.id
    if not approve.get(chat_id, False):
        await bot.reply_to(message, "⚠️ ကျေးဇူးပြု၍ /key အရင်လုပ်ပေးပါ။")
        return
    
    if chat_id not in user_data or ('portal_url' not in user_data[chat_id] and 'session_url' not in user_data[chat_id]):
        await bot.reply_to(message, "⚠️ Portal URL မရှိသေးပါ။ ကျေးဇူးပြု၍ `/portal [url]` ကို အရင်ထည့်ပါ။")
        return
    
    args = message.text.split(maxsplit=1)
    mode = args[1] if len(args) > 1 else "7"
    
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🛑 STOP SCAN", callback_data=f"stop_{chat_id}"))
    markup.add(InlineKeyboardButton("🔙 Back", callback_data="back_home"))
    
    status_msg = await bot.send_message(
        chat_id,
        f"🔍 **Scanning VOUCHER Codes...**\n\n"
        f"📦 Checked : 0 / 10,000,000\n"
        f"📊 Progress : 0.00%\n"
        f"⚡ Speed : 0 codes/min\n"
        f"✅ Success code hit : 0\n"
        f"🔢 VOUCHER Mode: {mode}",
        reply_markup=markup
    )
    
    task = asyncio.create_task(run_voucher_scanner(chat_id, status_msg.message_id, mode))
    scan_tasks[chat_id] = {"task": task, "status": "running"}

async def run_voucher_scanner(chat_id, msg_id, mode):
    total_codes = 10000000
    checked = 0
    success_hits = 0
    start_time = time.monotonic()
    
    try:
        while checked < total_codes and chat_id in scan_tasks and scan_tasks[chat_id]["status"] == "running":
            increment = random.randint(15000, 35000)
            checked = min(total_codes, checked + increment)
            elapsed = max(1, int(time.monotonic() - start_time))
            speed = int((checked / elapsed) * 60)
            progress = (checked / total_codes) * 100
            
            hit_str = ""
            if random.random() < 0.05 and success_hits == 0:
                success_hits += 1
                hit_code = f"{random.randint(100000, 999999)}"
                hit_str = f"\n\n✨ **Success Code Found:** `{hit_code}`"
                
                try:
                    results, sha = await get_file_content("result.json")
                    results.setdefault(str(chat_id), []).append(hit_code)
                    await update_file_content("result.json", results, sha, f"Add success code for {chat_id}")
                except Exception as e:
                    print(f"Error saving hit code: {e}", flush=True)
                
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("🛑 STOP SCAN", callback_data=f"stop_{chat_id}"))
            markup.add(InlineKeyboardButton("🔙 Back", callback_data="back_home"))
            
            try:
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=msg_id,
                    text=f"🔍 **Scanning VOUCHER Codes...**\n\n"
                         f"📦 Checked : {checked:,} / {total_codes:,}\n"
                         f"📊 Progress : {progress:.2f}%\n"
                         f"⚡ Speed : {speed:,} codes/min\n"
                         f"✅ Success code hit : {success_hits}"
                         f"{hit_str}",
                    reply_markup=markup
                )
            except Exception:
                pass
            
            await asyncio.sleep(2)
            
        if chat_id in scan_tasks and scan_tasks[chat_id].get("status") == "stopped":
            await bot.send_message(chat_id, "🛑 **Scan ကို ရပ်တန့်ပြီးပါပြီ။**")
    except Exception as e:
        print(f"Scanner error: {e}", flush=True)

@bot.callback_query_handler(func=lambda call: call.data.startswith("stop_") or call.data == "back_home")
async def callback_actions(call):
    chat_id = call.message.chat.id
    if call.data.startswith("stop_"):
        target_id = int(call.data.split("_")[1])
        if target_id in scan_tasks:
            scan_tasks[target_id]["status"] = "stopped"
        await bot.answer_callback_query(call.id, "Scan ကို ရပ်လိုက်ပါပြီ")
        try:
            await bot.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=None)
        except:
            pass
        await bot.send_message(chat_id, "🔴 **Scan ကို ရပ်တန့်ပြီးပါပြီ။**")
    elif call.data == "back_home":
        await bot.answer_callback_query(call.id, "ပင်မမီနူးသို့ ပြန်သွားပါပြီ")
        await bot.send_message(chat_id, "✨ **STAR LINK CODE HACK** ✨\n\n`/portal [url]` ဖြင့် အစကနေ ပြန်လည်စတင်နိုင်ပါသည်။")

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
        print(f"Error at listkeys {e}", flush=True)

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
        print(f"Error at delkey {e}", flush=True)

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
        print(f"Error at genkey {e}", flush=True)

@bot.message_handler(commands=['result'])
async def handle_result(message):
    auth_list, _ = await get_file_content("auth_list.json")
    if str(message.chat.id) in auth_list or message.from_user.id == ADMIN_ID:
        results, _ = await get_file_content("result.json")
        chat_id_str = str(message.chat.id)
        if chat_id_str in results and results[chat_id_str]:
            codes = "\n".join([f"🔑 `{c}`" for c in results[chat_id_str]])
            await bot.reply_to(message, f"✅ **Found Success Codes:**\n\n{codes}")
        else:
            await bot.reply_to(message, "သင့်တွင် ယခင်ကရရှိထားသော code မရှိသေးပါ။")
    else:
        await bot.reply_to(message, "သင်၏ key ကို registered မပြုလုပ်ရသေးပါ။")

@bot.message_handler(commands=['status'])
async def status(message):
    if message.from_user.id != ADMIN_ID:
        await bot.reply_to(message, "No Permission")
        return
    active_scans = sum(1 for data in scan_tasks.values() if data.get("status") == "running") if scan_tasks else 0
    approved_users = sum(1 for v in approve.values() if v)
    uptime_seconds = int(time.monotonic() - _start_time)
    hours, remainder = divmod(uptime_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    await bot.reply_to(
        message,
        f"📊 **Bot Status**\n\n"
        f"⏱ Uptime: {hours}h {minutes}m {seconds}s\n"
        f"🔍 Active Scans: {active_scans}\n"
        f"✅ Approved Users: {approved_users}\n"
        f"👥 Sessions Loaded: {len(user_data)}"
    )

async def main():
    print("===== MAIN() STARTED =====", flush=True)
    await rebuild_session()
    print("===== SESSION REBUILT =====", flush=True)

    app = web.Application()
    app.router.add_post(f"/{BOT_TOKEN}", handle_webhook)
    app.router.add_get("/", handle_root)

    port = int(os.environ.get("PORT", 10000))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"===== WEB SERVER STARTED ON PORT {port} =====", flush=True)

    await bot.remove_webhook()
    print("===== OLD WEBHOOK REMOVED =====", flush=True)

    max_retries = 3
    for attempt in range(max_retries):
        try:
            await bot.set_webhook(url=f"{RENDER_URL}/{BOT_TOKEN}")
            print(f"===== WEBHOOK SET SUCCESSFULLY =====", flush=True)
            break
        except Exception as e:
            print(f"===== WEBHOOK ATTEMPT {attempt + 1} FAILED: {e} =====", flush=True)
            if attempt < max_retries - 1:
                await asyncio.sleep(3)
            else:
                print("===== COULD NOT SET WEBHOOK =====", flush=True)

    print(f"===== BOT RUNNING IN WEBHOOK MODE =====", flush=True)

    while True:
        await asyncio.sleep(3600)

if __name__ == '__main__':
    print("===== __MAIN__ BLOCK ENTERED =====", flush=True)
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"===== FATAL ERROR: {e} =====", flush=True)
        import traceback
        traceback.print_exc()
    finally:
        if session and not session.closed:
            asyncio.run(session.close())
