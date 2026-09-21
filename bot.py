import telebot, asyncio, aiohttp, json, base64, random, re, os, string, time, uuid
from telebot.async_telebot import AsyncTeleBot
from aiohttp import web
import cv2
import numpy as np
from datetime import datetime, timedelta, timezone

# GPU error မတက်စေရန် CPU သီးသန့်သုံးဖို့ အမိန့်ပေးခြင်း
os.environ["ONNXRUNTIME_PROVIDER_NAME"] = "CPUExecutionProvider"
import ddddocr

# ================= CONFIG =================
# 💡 သင်ပေးထားသော Token အသစ်စက်စက်အား ဤနေရာတွင် တခါတည်း လဲလှယ်ပေးထားပါသည်
BOT_TOKEN = '8851853713:AAH0OhysnhQsCqgpN4Z0Bg-hVowD-E_aU3A'
GITHUB_TOKEN = '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'
REPO_OWNER = "htetaungkyaw256163038-cpu"
REPO_NAME = "Htet-Gyi"
ADMIN_ID = "2096430319"

# ================= GLOBAL =================
SUCCESS_CODE = asyncio.Queue()
bot = AsyncTeleBot(BOT_TOKEN)
approve = {}
user_data = {}
_voucher_sem = None

session = None
_connector = None

CONCURRENCY = 100
BATCH_SIZE = 500

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
    _connector = aiohttp.TCPConnector(limit=500, ttl_dns_cache=300, ssl=False)
    session = aiohttp.ClientSession(timeout=timeout, connector=_connector)

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

def check_key_expiration(key_data):
    if not isinstance(key_data, dict): return False
    expires = key_data.get("expires_at", "")
    if expires == "9999-12-31T23:59:59Z": return True
    try:
        exp_dt = datetime.fromisoformat(expires.replace("Z", "+00:00"))
        return datetime.now(timezone.utc) < exp_dt
    except:
        return False

async def get_file_content(path):
    url = f"https://github.com{REPO_OWNER}/{REPO_NAME}/contents/{path}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    try:
        async with session.get(url, headers=headers) as response:
            if response.status == 200:
                data = await response.json()
                content = base64.b64decode(data['content']).decode('utf-8')
                return json.loads(content), data['sha']
    except Exception as e:
        print(f"Error getting file {path}: {e}")
    return {}, None

async def update_file_content(path, content, sha, message):
    url = f"https://github.com{REPO_OWNER}/{REPO_NAME}/contents/{path}"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Content-Type": "application/json"
    }
    encoded = base64.b64encode(json.dumps(content).encode()).decode()
    payload = {"message": message, "content": encoded, "sha": sha}
    try:
        async with session.put(url, headers=headers, json=payload) as response:
            return await response.text()
    except Exception as e:
        print(f"Error updating file {path}: {e}")

# ================= TELEGRAM HANDLERS =================

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
            await bot.reply_to(message, "Key မှန်ကန်ပါသည်။ /input ဖြင့် စကင်ဖတ်မည့် ဂဏန်းအကွာအဝေးကို သတ်မှတ်ပါ။\n\nဥပမာ- `/input 1000000 2000000`")
        else:
            approve[message.chat.id] = False
            await bot.reply_to(message, "Key Expired ဖြစ်နေပါသည်။")
    else:
        await bot.reply_to(message, "သင်၏ key ကို registered မလုပ်ရသေးပါ။")

@bot.message_handler(commands=['genkey'])
async def genkey(message):
    if str(message.chat.id) != ADMIN_ID: return
    try:
        args = message.text.split()
        if len(args) < 3: return
        plan = args[1]
        user_id = args[2]
        expiry = generate_expiry(plan)
        if not expiry: return
        auth_list, sha = await get_file_content("auth_list.json")
        auth_list[user_id] = {"expires_at": expiry, "plan": plan}
        await update_file_content("auth_list.json", auth_list, sha, f"Add key for {user_id}")
        await bot.reply_to(message, f"Key Generated\n\nUSER ID : {user_id}\nPLAN : {plan}")
    except Exception as e:
        print(e)

@bot.message_handler(commands=['input'])
async def handle_input(message):
    chat_id = message.chat.id
    if not approve.get(chat_id, False):
        await bot.reply_to(message, "⚠️ သင့်မှာ ခွင့်ပြုချက်မရှိပါ။ အရင်ဆုံး /key ကို နှိပ်ပါ။")
        return
    try:
        args = message.text.split()
        if len(args) < 3:
            await bot.reply_to(message, "ℹ️ ဥပမာ- `/input 1000000 2000000`")
            return
        start_num = int(args[1])
        end_num = int(args[2])
        status_msg = await bot.reply_to(message, "🚀 Voucher စကင်ဖတ်ခြင်းကို ပြင်ဆင်နေပါသည်...")
        asyncio.create_task(start_scanning_process(chat_id, start_num, end_num, status_msg))
    except Exception as e:
        print(e)

# ================= CORE SCAN ENGINE =================

async def check_voucher_api(voucher_code):
    global session, _voucher_sem
    async with _voucher_sem:
        target_url = f"https://httpbin.org{voucher_code}" 
        try:
            async with session.get(target_url, timeout=5) as resp:
                if resp.status == 200:
                    return {"code": voucher_code, "status": "SUCCESS"}
        except:
            pass
        return {"code": voucher_code, "status": "FAILED"}

async def start_scanning_process(chat_id, start_num, end_num, status_msg):
    global _voucher_sem
    if _voucher_sem is None:
        _voucher_sem = asyncio.Semaphore(CONCURRENCY)
    
    await bot.edit_message_text("🔍 စကင်ဖတ်ခြင်း စတင်ပါပြီ...", chat_id, status_msg.message_id)
    
    current_batch = []
    for code in range(start_num, end_num + 1):
        current_batch.append(check_voucher_api(code))
        if len(current_batch) >= BATCH_SIZE or code == end_num:
            results = await asyncio.gather(*current_batch)
            current_batch = []
            
            success_codes = [r["code"] for r in results if r["status"] == "SUCCESS"]
            if success_codes:
                res_data, sha = await get_file_content("result.json")
                if str(chat_id) not in res_data: res_data[str(chat_id)] = []
                res_data[str(chat_id)].extend(success_codes)
                await update_file_content("result.json", res_data, sha, f"Found {len(success_codes)} codes")
                await bot.send_message(chat_id, f"🎉 Voucher အသစ်တွေ့ရှိသည် -\n" + "\n".join(map(str, success_codes)))
                
    await bot.edit_message_text("✅ စကင်ဖတ်ခြင်း ပြီးဆုံးပါပြီ။", chat_id, status_msg.message_id)

async def main():
    await rebuild_session()
    await web_server()
    print("Bot is polling...")
    await bot.infinity_polling()

if __name__ == "__main__":
    asyncio.run(main())
