FROM python:3.10

# ဆာဗာအတွင်းပိုင်းကို Update လုပ်ပြီး ddddocr အတွက် လိုအပ်သော Libraries များ ထည့်သွင်းခြင်း
RUN apt-get update && apt-get install -y \
    libgl1-mesa-glx \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# pip ကို Upgrade လုပ်ပြီး packages များ ထည့်သွင်းခြင်း
RUN pip install --no-cache-dir --upgrade pip
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "bot.py"]
