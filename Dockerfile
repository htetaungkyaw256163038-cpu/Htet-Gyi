# 1. Base Image ကို လုံခြုံရေးစနစ် ကိုက်ညီမည့် Ubuntu သို့ ပြောင်းလဲအသုံးပြုပါသည်
FROM ubuntu:20.04

# 2. Timezone အမေးများကို ကျော်ရန်နှင့် Environment သတ်မှတ်ရန်
ENV DEBIAN_FRONTEND=noninteractive
ENV WORKDIR /app
WORKDIR /app

# 3. ddddocr အတွက် လိုအပ်သော Linux packages များနှင့် Python 3.10 ထည့်သွင်းခြင်း
RUN apt-get update && apt-get install -y \
    python3.10 \
    python3-pip \
    python3.10-dev \
    libgl1 \
    libglx-mesa0 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# 4. pip ကို update လုပ်ခြင်း
RUN python3.10 -m pip install --upgrade pip

# 5. လိုအပ်သော package စာရင်းများကို ကူးယူပြီး install လုပ်ခြင်း
COPY requirements.txt .
RUN python3.10 -m pip install --no-cache-dir -r requirements.txt

# 6. Project အတွင်းရှိ ဖိုင်အားလုံးကို Container ထဲ ကူးထည့်ခြင်း
COPY . .

# 7. Render အတွက် Port ဖွင့်ပေးခြင်း
EXPOSE 10000

# 8. စတင်ပတ်မည့် Command
CMD ["python3.10", "bot.py"]
