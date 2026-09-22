import os
import threading
import time
import random
import asyncio
from flask import Flask
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# Render အတွက် Port ချိတ်ဆက်ပေးမည့် Dummy Web Server
app = Flask('')

@app.route('/')
def home():
    return "Bot is running!"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# Background တွင် Web Server စတင်ခြင်း
threading.Thread(target=run_web).start()

# Telegram Bot Token သတ်မှတ်ခြင်း (သို့မဟုတ် Environment Variable မှ ယူရန်)
TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN")
bot = telebot.TeleBot(TOKEN)

scan_tasks = {}

async def get_file_content(filename):
    return {}, ""

async def update_file_content(filename, results, sha, message):
    pass

# Voucher Scanner Async Function (၆ လုံး၊ ၇ လုံး၊ ၈ လုံး Mode မှန်ကန်စေရန်)
async def run_voucher_scanner(chat_id, msg_id, mode):
    if mode == "6":
        min_val, max_val = 100000, 999999
        total_codes = 900000
    elif mode == "7":
        min_val, max_val = 1000000, 9999999
        total_codes = 9000000
    elif mode == "8":
        min_val, max_val = 10000000, 99999999
        total_codes = 90000000
    elif mode == "ascii":
        min_val, max_val = 1000000, 9999999
        total_codes = 10000000
    else: 
        min_val, max_val = 1000000, 9999999
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
                hit_code = str(random.randint(min_val, max_val))
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
                bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=msg_id,
                    text=f"🔍 **Scanning VOUCHER Codes...**\n\n"
                         f"📦 Checked : {checked:,} / {total_codes:,}\n"
                         f"📊 Progress : {progress:.2f}%\n"
                         f"⚡ Speed : {speed:,} codes/min\n"
                         f"✅ Success code hit : {success_hits}"
                         f"{hit_str}",
                    reply_markup=markup,
                    parse_mode="Markdown"
                )
            except Exception:
                pass
            
            await asyncio.sleep(2)
            
        if chat_id in scan_tasks and scan_tasks[chat_id].get("status") == "stopped":
            bot.send_message(chat_id, "🛑 **Scan ကို ရပ်တန့်ပြီးပါပြီ။**", parse_mode="Markdown")
    except Exception as e:
        print(f"Scanner error: {e}", flush=True)

@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, "မင်္ဂလာပါ! Bot အဆင်သင့် ဖြစ်ပါပြီ။")

if __name__ == "__main__":
    bot.infinity_polling()
