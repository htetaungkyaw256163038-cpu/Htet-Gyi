import telebot, asyncio, aiohttp, json, base64, random
from telebot.async_telebot import AsyncTeleBot
from aiohttp import web
import cv2
import dddocr
import numpy as np
from datetime import datetime, timedelta, timezone

TOKEN = 'ဒီနေရာမှာ_သင့်ရဲ့_Bot_Token_အရှည်ကြီးကို_ထည့်ပါ'
_TOKEN = ''
OWNER = ""
NAME = ""
