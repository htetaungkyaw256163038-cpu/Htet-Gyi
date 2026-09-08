import telebot, asyncio, aiohttp, json
from telebot.async_telebot import AsyncTeleBot
from aiohttp import web
import cv2
import ddddocr
import os

import numpy as np
from datetime import datetime, timedelta

TOKEN = '8851853713:AAHoF5wvoib3FOsH6adR9w586vM-jO4G39U'
_TOKEN = ''
OWNER = ""
NAME = ""

# Bot Instance ကို ကြေညာခြင်း
bot = AsyncTeleBot(TOKEN)

# ၁။ သင့်ရဲ့ မူရင်း Bot Logic ကုဒ်များ (Message Handlers)
@bot.message_handler(commands=['start', 'help'])
async def send_welcome(message):
    await bot.reply_to(message, "မင်္ဂလာပါ! Bot အောင်မြင်စွာ အလုပ်လုပ်နေပါပြီ။")

@bot.message_handler(func=lambda message: True)
async def echo_all(message):
    await bot.reply_to(message, message.text)


# ၂။ Render အတွက် မဖြစ်မနေလိုအပ်သော Web Server အပိုင်း
async def handle_web(request):
    return web.Response(text="Bot is running smoothly!")

async def main():
    app = web.Application()
    app.router.add_get('/', handle_web)
    
    # Render က သတ်မှတ်ပေးတဲ့ PORT နံပါတ်ကို ဖတ်ခြင်း
    port = int(os.environ.get("PORT", 10000))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port)
    
    print("Starting Web Server and Bot polling...")
    # Web Server ရော Telegram Bot ရော နှစ်ခုလုံးကို ပြိုင်တူ Run ခိုင်းခြင်း
    await asyncio.gather(
        site.start(),
        bot.polling(non_stop=True)
    )

if __name__ == '__main__':
    asyncio.run(main())
