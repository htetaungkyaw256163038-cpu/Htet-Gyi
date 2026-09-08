import telebot
import asyncio
import aiohttp
import json
from telebot.async_telebot import AsyncTeleBot
from aiohttp import web
import cv2
import ddddocr
import os

import numpy as np
from datetime import datetime, timedelta

# Bot API Token အသစ်ကို ဖြည့်သွင်းခြင်း
TOKEN = '8851853713:AAHOF5wvoib3F0sH6adR9wCn3buGVuOR3Ww'
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
    return web.Response(text="Bot is running smoothly.")

app = web.Application()
app.router.add_get('/', handle_web)

async def main():
    # Web Server ကို background မှာ ပတ်ထားခြင်း
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', int(os.environ.get('PORT', 8080)))
    await site.start()
    
    # Telegram Bot ကို စတင် Run ခြင်း
    print("Bot က စတင်အလုပ်လုပ်နေပါပြီ...")
    await bot.infinity_polling()

if __name__ == '__main__':
    asyncio.run(main())
