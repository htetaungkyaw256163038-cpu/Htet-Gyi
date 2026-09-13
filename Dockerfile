# 1. Base Image အဖြစ် တရားဝင် Python Image ကို သုံးပါမည်
FROM python:3.10-slim

# 2. Container အတွင်း အလုပ်လုပ်မည့် Folder သတ်မှတ်ခြင်း
WORKDIR /app

# 3. ONNX GPU Error များ မတက်စေရန် Environment သတ်မှတ်ခြင်း
ENV ONNXRUNTIME_PROVIDERS=CPUExecutionProvider

# 4. အမှားတက်နေသော apt-get install စာကြောင်းများကို အကုန်ဖြုတ်ချပြီး 
#    စနစ်ကို Update သက်သက်သာ အမြန်လုပ်ခိုင်းခြင်း
RUN apt-get update && apt-get install -y --no-install-recommends \
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
