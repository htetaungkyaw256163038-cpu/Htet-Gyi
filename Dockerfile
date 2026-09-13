# 1. Base Image ကို အမှားကင်းစင်သော Python Debian Bullseye သို့ ပြောင်းလဲပါသည်
FROM python:3.10-slim-bullseye

# 2. Container အတွင်း အလုပ်လုပ်မည့် Folder သတ်မှတ်ခြင်း
WORKDIR /app

# 3. ONNX GPU Error နှင့် လုံခြုံရေးအမေးများ ကျော်ရန် Environment သတ်မှတ်ခြင်း
ENV ONNXRUNTIME_PROVIDERS=CPUExecutionProvider
ENV DEBIAN_FRONTEND=noninteractive

# 4. ddddocr / OpenCV အတွက် လိုအပ်သော Linux Packages များ ထည့်သွင်းခြင်း
RUN apt-get update && apt-get install -y \
    libgl1-mesa-glx \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# 5. လိုအပ်သော package စာရင်းများကို ကူးယူပြီး install လုပ်ခြင်း
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 6. Project အတွင်းရှိ ဖိုင်အားလုံးကို Container ထဲ ကူးထည့်ခြင်း
COPY . .

# 7. Render အတွက် Port ဖွင့်ပေးခြင်း
EXPOSE 10000

# 8. Bot ကို စတင်ပတ်မည့် Command
CMD ["python", "bot.py"]
