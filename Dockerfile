# Ubuntu Base Image ကို ပြောင်းသုံးခြင်းဖြင့် လိုအပ်သော Linux Libraries များ တစ်ခါတည်း အပြည့်အစုံ ပါဝင်လာပါမည်
FROM python:3.10

WORKDIR /app

# pip ကို အရင်ဆုံး Update လုပ်ခြင်း
RUN pip install --no-cache-dir --upgrade pip

# လိုအပ်သော Packages များ ထည့်သွင်းခြင်း
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "bot.py"]
