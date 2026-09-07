import telebot, asyncio, aiohttp, json, base64, random
from telebot.async_telebot import AsyncTeleBot
from aiohttp import web
import cv2
import dddocr

import numpy as np
from datetime import datetime, timedelta, timezone

TOKEN = '8851853713:AAHoF5wvoib3F0sH6adR9wCn3buGVuOR3Ww'
_TOKEN = ''
OWNER = ""
NAME = ""
