import telebot, asyncio, aiohttp, json, base64, random, re, os, string, time, uuid, concurrent.futures
from telebot.async_telebot import AsyncTeleBot
from aiohttp import web
import cv2
import ddddocr
import numpy as np
from datetime import datetime, timedelta, timezone

BOT_TOKEN = '8304019935:AAGvHTXAaVsLyfYI6xZZydlyT2QY2CJCEeg'
GITHUB_TOKEN = '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'
REPO_OWNER = "htetaungkyaw256163038-cpu"
REPO_NAME = "Htet-Gyi"
ADMIN_ID = "2096430319"

bot = AsyncTeleBot(BOT_TOKEN)
_telegram_send = bot.send_message
_telegram_reply = bot.reply_to
_telegram_edit = bot.edit_message_text
user_data = {}
redeem_access = {}
redeem_lock = asyncio.Lock()
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

async def _drain_stdout(proc, idx):
    if proc and proc.stdout:
        try:
            async for _ in proc.stdout:
                pass
        except Exception:
            pass

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
    }
    if sha:
        payload["sha"] = sha
    async with session.put(url, headers=headers, json=payload) as response:
        return await response.text()

TELEGRAM_MESSAGE_LIMIT = 3900
TELEGRAM_RETRY_LIMIT = 3

def split_telegram_message(text, max_chars=TELEGRAM_MESSAGE_LIMIT):
    if len(text) <= max_chars:
        return [text]
    chunks = []
    remaining = text
    while remaining:
        cut = min(max_chars, len(remaining))
        if cut < len(remaining):
            newline = remaining.rfind("\n", 0, cut)
            if newline > 0:
                cut = newline
        chunks.append(remaining[:cut].rstrip())
        remaining = remaining[cut:].lstrip()
    return chunks

async def safe_send_message(chat_id, text, **kwargs):
    for attempt in range(TELEGRAM_RETRY_LIMIT):
        try:
            return await _telegram_send(chat_id, text, **kwargs)
        except (asyncio.TimeoutError, aiohttp.ClientError) as error:
            if attempt == TELEGRAM_RETRY_LIMIT - 1:
                raise
            print(f"[telegram] send retry {attempt + 1}/{TELEGRAM_RETRY_LIMIT}: {error}")
            await asyncio.sleep(1 + attempt)

async def safe_reply_to(message, text, **kwargs):
    for attempt in range(TELEGRAM_RETRY_LIMIT):
        try:
            return await _telegram_reply(message, text, **kwargs)
        except (asyncio.TimeoutError, aiohttp.ClientError) as error:
            if attempt == TELEGRAM_RETRY_LIMIT - 1:
                raise
            print(f"[telegram] reply retry {attempt + 1}/{TELEGRAM_RETRY_LIMIT}: {error}")
            await asyncio.sleep(1 + attempt)

async def safe_edit_message_text(chat_id, message_id, text, **kwargs):
    for attempt in range(TELEGRAM_RETRY_LIMIT):
        try:
            return await _telegram_edit(
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                **kwargs
            )
        except (asyncio.TimeoutError, aiohttp.ClientError) as error:
            if attempt == TELEGRAM_RETRY_LIMIT - 1:
                raise
            print(f"[telegram] edit retry {attempt + 1}/{TELEGRAM_RETRY_LIMIT}: {error}")
            await asyncio.sleep(1 + attempt)

async def update_chunked_messages(chat_id, title, items, message_ids=None):
    chunks = split_telegram_message(f"{title}\n\n" + "\n\n".join(items))
    message_ids = list(message_ids or [])
    for index, chunk in enumerate(chunks):
        if index < len(message_ids):
            try:
                await safe_edit_message_text(chat_id, message_ids[index], chunk)
                continue
            except Exception as error:
                print(f"[telegram] edit failed after retries: {error}")
        sent = await safe_send_message(chat_id, chunk)
        if index < len(message_ids):
            message_ids[index] = sent.message_id
        else:
            message_ids.append(sent.message_id)
    return message_ids

bot.send_message = safe_send_message
bot.reply_to = safe_reply_to
bot.edit_message_text = safe_edit_message_text

@bot.message_handler(commands=['start'])
async def start(message):
    await bot.reply_to(message, "Bot စတင်ပါပြီ။ /redeem <code> ဖြင့် access ရယူပါ။")

def generate_redeem_code(existing_codes):
    alphabet = string.ascii_uppercase + string.digits
    while True:
        code = ''.join(random.choice(alphabet) for _ in range(6))
        if code not in existing_codes:
            return code

async def redeem_user_access(chat_id):
    access = redeem_access.get(chat_id)
    if not access or access.get("uses_remaining", 0) <= 0:
        return False
    return True

async def consume_redeem_use(chat_id):
    async with redeem_lock:
        access = redeem_access.get(chat_id)
        if not access or access.get("uses_remaining", 0) <= 0:
            return False
        codes, sha = await get_file_content("redeem_codes.json")
        code = access["code"]
        entry = codes.get(code)
        if not entry or entry.get("claimed_by") != str(chat_id):
            redeem_access.pop(chat_id, None)
            return False
        remaining = int(entry.get("uses_remaining", 0))
        if remaining <= 0:
            redeem_access.pop(chat_id, None)
            return False
        entry["uses_remaining"] = remaining - 1
        await update_file_content(
            "redeem_codes.json", codes, sha,
            f"Consume redeem code {code} for {chat_id}"
        )
        access["uses_remaining"] = remaining - 1
        if access["uses_remaining"] <= 0:
            redeem_access.pop(chat_id, None)
        return True

@bot.message_handler(commands=['redeem'])
async def redeem(message):
    args = message.text.split()
    if len(args) != 2 or not re.fullmatch(r"[A-Z0-9]{6}", args[1].upper()):
        await bot.reply_to(message, "Usage: /redeem ABC123")
        return
    code = args[1].upper()
    chat_id = str(message.chat.id)
    async with redeem_lock:
        codes, sha = await get_file_content("redeem_codes.json")
        entry = codes.get(code)
        if not entry:
            await bot.reply_to(message, "Redeem code မတွေ့ပါ။")
            return
        claimed_by = entry.get("claimed_by")
        if claimed_by and claimed_by != chat_id:
            await bot.reply_to(message, "ဒီ redeem code ကို အခြား user က အသုံးပြုပြီးပါပြီ။")
            return
        remaining = int(entry.get("uses_remaining", 0))
        if remaining <= 0:
            await bot.reply_to(message, "ဒီ redeem code ရဲ့ access time ကုန်ဆုံးပါပြီ။")
            return
        entry["claimed_by"] = chat_id
        entry["claimed_at"] = datetime.now(timezone.utc).isoformat()
        await update_file_content(
            "redeem_codes.json", codes, sha,
            f"Redeem code {code} by {chat_id}"
        )
        redeem_access[message.chat.id] = {
            "code": code,
            "uses_remaining": remaining,
        }
    user_data[message.chat.id] = {}
    await bot.reply_to(message, f"Redeem အောင်မြင်ပါသည်။ Scan access ကျန်ရှိမှု: {remaining}")

@bot.message_handler(commands=['genredeem'])
async def genredeem(message):
    if str(message.chat.id) != ADMIN_ID:
        await bot.reply_to(message, "No Permission")
        return
    args = message.text.split()
    if len(args) not in (2, 3) or not args[1].isdigit() or int(args[1]) < 1:
        await bot.reply_to(message, "Usage: /genredeem <scan-count> [count]")
        return
    uses = int(args[1])
    count = int(args[2]) if len(args) == 3 and args[2].isdigit() else 1
    if count < 1 or count > 100:
        await bot.reply_to(message, "count သည် 1 မှ 100 အတွင်း ဖြစ်ရပါမည်။")
        return
    async with redeem_lock:
        codes, sha = await get_file_content("redeem_codes.json")
        generated = []
        for _ in range(count):
            code = generate_redeem_code(codes)
            codes[code] = {
                "uses_total": uses,
                "uses_remaining": uses,
                "claimed_by": None,
                "claimed_at": None,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            generated.append(code)
        await update_file_content(
            "redeem_codes.json", codes, sha,
            f"Generate {count} redeem code(s)"
        )
    await bot.reply_to(message, "Generated redeem code(s):\n" + "\n".join(generated))

@bot.message_handler(commands=['listredeem'])
async def listredeem(message):
    if str(message.chat.id) != ADMIN_ID:
        await bot.reply_to(message, "No Permission")
        return
    codes, _ = await get_file_content("redeem_codes.json")
    if not codes:
        await bot.reply_to(message, "Redeem code မရှိသေးပါ။")
        return
    lines = [
        f"{code} | {entry.get('uses_remaining', 0)}/{entry.get('uses_total', 0)} | "
        f"user: {entry.get('claimed_by') or '-'}"
        for code, entry in codes.items()
    ]
    for index, chunk in enumerate(split_telegram_message("Redeem codes:\n" + "\n".join(lines))):
        if index == 0:
            await bot.reply_to(message, chunk)
        else:
            await safe_send_message(message.chat.id, chunk)

async def check_session_url(session_url):
    headers = {
        'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'accept-language': 'en-US,en;q=0.9',
        'priority': 'u=0, i',
        'referer': session_url,
        'sec-ch-ua': '"Chromium";v="148", "Microsoft Edge";v="148", "Not/A)Brand";v="99"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Android"',
        'sec-fetch-dest': 'document',
        'sec-fetch-mode': 'navigate',
        'sec-fetch-site': 'same-origin',
        'upgrade-insecure-requests': '1',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36 Edg/148.0.0.0',
        'cookie': 'sensorsdata2015jssdkcross=%7B%22distinct_id%22%3A%2219e0ddbd9f2152-0df941f2efc6b08-4c657b58-1327104-19e0ddbd9f3a60%22%2C%22first_id%22%3A%22%22%2C%22props%22%3A%7B%22%24latest_traffic_source_type%22%3A%22%E8%87%AA%E7%84%B6%E6%90%9C%E7%B4%A2%E6%B5%81%E9%87%8F%22%2C%22%24latest_search_keyword%22%3A%22%E6%9C%AA%E5%8F%96%E5%88%B0%E5%80%BC%22%2C%22%24latest_referrer%22%3A%22https%3A%2F%2Fgemini.google.com%2F%22%7D%2C%22identities%22%3A%22eyIkaWRlbnRpdHlfY29va2llX2lkIjoiMTllMGRkYmQ5ZjIxNTItMGRmOTQxZjJlZmM2YjA4LTRjNjU3YjU4LTEzMjcxMDQtMTllMGRkYmQ5ZjNhNjAifQ%3D%3D%22%2C%22history_login_id%22%3A%7B%22name%22%3A%22%22%2C%22value%22%3A%22%22%7D%2C%22%24device_id%22%3A%2219e0ddbd9f2152-0df941f2efc6b08-4c657b58-1327104-19e0ddbd9f3a60%22%7D'
    }
    try:
        async with session.get(session_url, allow_redirects=True, headers=headers) as response:
            final_url = str(response.url)
            body = await response.text()
            print(f"[check_session_url] final_url={final_url} status={response.status}")
            if "sessionId" in final_url or "sessionId" in body:
                return True
            if response.status in (200, 302, 301):
                return True
            return False
    except Exception as e:
        print(f"[check_session_url] error: {e}")
        return False
