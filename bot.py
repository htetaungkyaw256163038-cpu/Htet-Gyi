import telebot, asyncio, aiohttp, json, base64, random, re, os, string, time, uuid, concurrent.futures
from telebot.async_telebot import AsyncTeleBot
from aiohttp import web
import cv2
import ddddocr
import numpy as np
from datetime import datetime, timedelta, timezone

# --- RAM ချွေတာရန်နှင့် CPU သုံးရန် သတ်မှတ်ချက်များ ---
os.environ["ONNXRUNTIME_PROVIDER_DEFAULT_TO_CPU"] = "1"
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"

# --- BOT CONFIGURATION ---
BOT_TOKEN = '8982068568:AAEs06DuLsA3c69HYYcYNf_b61lAyNmtaA4'
GITHUB_TOKEN = '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'
REPO_OWNER = "htetaungkyaw25163038-cpu"
REPO_NAME = "Htet-Gyi"
ADMIN_ID = "5411776510"  # သင့် Telegram Chat ID ကို ဖြည့်စွက်ပေးထားပါသည်

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

# --- Helper Functions ---

def generate_expiry(plan):
    now = datetime.now(timezone.utc)
    if plan == "30m": return (now + timedelta(minutes=30)).isoformat() + "Z"
    if plan == "1h": return (now + timedelta(hours=1)).isoformat() + "Z"
    if plan == "1d": return (now + timedelta(days=1)).isoformat() + "Z"
    if plan == "7d": return (now + timedelta(days=7)).isoformat() + "Z"
    if plan == "1m": return (now + timedelta(days=30)).isoformat() + "Z"
    if plan == "1y": return (now + timedelta(days=365)).isoformat() + "Z"
    if plan == "unlimited": return "9999-12-31T23:59:59Z"
    return None

def check_key_expiration(data):
    if isinstance(data, dict):
        expires = data.get("expires_at", "")
    else:
        expires = str(data)
    if expires == "9999-12-31T23:59:59Z": return True
    try:
        exp_dt = datetime.fromisoformat(expires.replace("Z", "+00:00"))
        return datetime.now(timezone.utc) < exp_dt
    except:
        return False

# --- Web Server ---

async def handle(request):
    return web.Response(text="Bot is awake and running 24/7!")

async def web_server():
    app = web.Application()
    app.router.add_get('/', handle)
    runner = web.AppRunner(app)
    await runner.setup()
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

# --- Telegram Bot Handlers ---

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
                "Key မှန်ကန်ပါသည်။ /input ဖြင့် Session URL ထည့်ပါ။"
            )
        else:
            approve[message.chat.id] = False
            await bot.reply_to(
                message,
                "Key Expired ဖြစ်နေပါသည်။"
            )
    else:
        await bot.reply_to(
            message,
            "သင်၏ key ကို registered မလုပ်ရသေးပါ။"
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
            f"Key Deleted\n\nUSER ID : {user_id}"
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
            f"Key Generated\n\n"
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
        try:
            results, _ = await get_file_content("result.json")
            chat_id_str = str(message.chat.id)
            if chat_id_str in results and results[chat_id_str]:
                codes = "\n".join(results[chat_id_str])
                await bot.reply_to(message, f"📋 ရလဒ်များ -\n\n{codes}")
            else:
                await bot.reply_to(message, "ပြသရန် ရလဒ်မရှိသေးပါ။")
        except Exception as e:
            print(f"Error at handle_result: {e}")
            await bot.reply_to(message, "ရလဒ်ဆွဲယူရာတွင် အမှားအယွင်းရှိခဲ့ပါသည်။")
    else:
