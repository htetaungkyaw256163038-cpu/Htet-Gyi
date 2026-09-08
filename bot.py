import telebot, asyncio, aiohttp, json, base64, random, re, os, string, time, uuid, concurrent.futures
from telebot.async_telebot import AsyncTeleBot
from aiohttp import web
import cv2, ddddocr, numpy as np
from datetime import datetime, timedelta, timezone

os.environ["ONNXRUNTIME_PROVIDER_DEFAULT_TO_CPU"] = "1"
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"

BOT_TOKEN = '8982068568:AAEs06DuLsA3c69HYYcYNf_b61lAyNmtaA4'
GITHUB_TOKEN = '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'
REPO_OWNER = "htetaungkyaw25163038-cpu"
REPO_NAME = "Htet-Gyi"
ADMIN_ID = "5411776510"

SUCCESS_CODE = asyncio.Queue()
bot = AsyncTeleBot(BOT_TOKEN)
user_data, approve, scan_tasks, success_messages, success_texts = {}, {}, {}, {}, {}
limited_messages, limited_texts, captcha_state, retry_counts, _session_pool = {}, {}, {}, {}, {}
session, _connector, _voucher_sem = None, None, None
_start_time = time.monotonic()
SESSION_POOL_LIMIT, SESSION_POOL_SLOTS, CONCURRENCY, BATCH_SIZE = 60, 5, 2500, 5000

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
    if isinstance(data, dict): expires = data.get("expires_at", "")
    else: expires = str(data)
    if expires == "9999-12-31T23:59:59Z": return True
    try: return datetime.now(timezone.utc) < datetime.fromisoformat(expires.replace("Z", "+00:00"))
    except: return False

async def handle(request):
    return web.Response(text="Bot is awake and running 24/7!")

async def web_server():
    app = web.Application()
    app.router.add_get('/', handle)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, '0.0.0.0', int(os.environ.get('PORT', 8099))).start()
    print("Web server started")

async def rebuild_session():
    global session, _connector
    if session and not session.closed: await session.close()
    if _connector and not _connector.closed: await _connector.close()
    _connector = aiohttp.TCPConnector(limit=6000, ttl_dns_cache=300, ssl=False)
    session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30), connector=_connector, connector_owner=False)

async def _drain_stdout(proc, idx):
    if proc and proc.stdout:
        try:
            async for _ in proc.stdout: pass
        except: pass

async def get_file_content(path):
    url = f"https://github.com{REPO_OWNER}/{REPO_NAME}/contents/{path}"
    async with session.get(url, headers={"Authorization": f"token {GITHUB_TOKEN}"}) as response:
        if response.status == 200:
            data = await response.json()
            return json.loads(base64.b64decode(data['content']).decode('utf-8')), data['sha']
    return {}, None

async def update_file_content(path, content, sha, message):
    url = f"https://github.com{REPO_OWNER}/{REPO_NAME}/contents/{path}"
    payload = {"message": message, "content": base64.b64encode(json.dumps(content).encode()).decode(), "sha": sha}
    async with session.put(url, headers={"Authorization": f"token {GITHUB_TOKEN}", "Content-Type": "application/json"}, json=payload) as r:
        return await r.text()

@bot.message_handler(commands=['start'])
async def start(message):
    await bot.reply_to(message, "Bot စတင်ပါပြီ။ /key ဖြင့်စတင်ပါ။")

@bot.message_handler(commands=['key'])
async def handle_key(message):
    global approve
    auth_list, _ = await get_file_content("auth_list.json")
    key = str(message.chat.id)
    if key in auth_list:
        if check_key_expiration(auth_list[key]):
            approve[message.chat.id] = True
            user_data[message.chat.id] = {}
            await bot.reply_to(message, "Key မှန်ကန်ပါသည်။ /input ဖြင့် Session URL ထည့်ပါ။")
        else:
            approve[message.chat.id] = False
            await bot.reply_to(message, "Key Expired ဖြစ်နေပါသည်။")
    else: await bot.reply_to(message, "သင်၏ key ကို registered မလုပ်ရသေးပါ။")

@bot.message_handler(commands=['listkeys'])
async def listkeys(message):
    if str(message.chat.id) != ADMIN_ID: return
    try:
        auth_list, _ = await get_file_content("auth_list.json")
        if not auth_list: return await bot.reply_to(message, "Registered key မရှိသေးပါ။")
        lines = []
        for uid, data in auth_list.items():
            if isinstance(data, dict):
                expires = data.get("expires_at", "unknown")
                plan = data.get("plan", "unknown")
                if expires == "9999-12-31T23:59:59Z": expires_str = "Unlimited"
                else:
                    try:
                        diff = datetime.fromisoformat(expires.replace("Z", "+00:00")) - datetime.now(timezone.utc)
                        expires_str = "Expired" if diff.total_seconds() < 0 else f"{diff.days}d {diff.seconds // 3600}h left"
                    except: expires_str = expires
            else: plan, expires_str = "old", str(data)
            lines.append(f"👤 {uid}\n   Plan: {plan}\n   Expires: {expires_str}")
        text = f"📋 Registered Keys ({len(auth_list)})\n\n" + "\n\n".join(lines)
        if len(text) > 4096:
            for i in range(0, len(text), 4096): await bot.send_message(message.chat.id, text[i:i+4096])
        else: await bot.reply_to(message, text)
    except Exception as e: print(f"Error {e}")

@bot.message_handler(commands=['delkey'])
async def delkey(message):
    if str(message.chat.id) != ADMIN_ID: return
    try:
        args = message.text.split()
        if len(args) < 2: return await bot.reply_to(message, "Usage: /delkey ID")
        user_id = args[1]
        auth_list, sha = await get_file_content("auth_list.json")
        if user_id not in auth_list: return await bot.reply_to(message, "မတွေ့ပါ။")
        del auth_list[user_id]
        await update_file_content("auth_list.json", auth_list, sha, f"Delete {user_id}")
        approve.pop(int(user_id), None)
        await bot.reply_to(message, f"Deleted: {user_id}")
    except Exception as e: print(f"Error {e}")

@bot.message_handler(commands=['genkey'])
async def genkey(message):
    if str(message.chat.id) != ADMIN_ID: return
    try:
        args = message.text.split()
        if len(args) < 3: return await bot.reply_to(message, "Usage: /genkey 1h ID")
        plan = args[1]
        user_id = args[2]
        expiry = generate_expiry(plan)
        if not expiry: return await bot.reply_to(message, "Plan မှားနေသည်။")
        auth_list, sha = await get_file_content("auth_list.json")
        auth_list[user_id] = {"expires_at": expiry, "plan": plan}
        await update_file_content("auth_list.json", auth_list, sha, f"Add {user_id}")
        await bot.reply_to(message, f"🔑 Generated\nID: {user_id}\nPlan: {plan}\nExpires: {expiry}")
    except Exception as e: print(f"Error {e}")

@bot.message_handler(commands=['result'])
async def handle_result(message):
    auth_list, _ = await get_file_content("auth_list.json")
    if str(message.chat.id) not in auth_list: return
    try:
        results, _ = await get_file_content("result.json")
        chat_id_str = str(message.chat.id)
        if chat_id_str in results and results[chat_id_str]:
            await bot.reply_to(message, f"📋 ရလဒ်များ -\n\n" + "\n".join(results[chat_id_str]))
        else: await bot.reply_to(message, "ပြသရန် ရလဒ်မရှိသေးပါ။")
    except Exception as e: print(f"Error {e}")

async def main():
    await rebuild_session()
    await asyncio.gather(web_server(), bot.polling(non_stop=True))

if __name__ == '__main__':
    asyncio.run(main())
