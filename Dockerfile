# 1. Base Image အဖြစ် Python ကို သုံးပါမည်
FROM python:3.10-slim

# 2. Container အတွင်း အလုပ်လုပ်မည့် Folder သတ်မှတ်ခြင်း
WORKDIR /app

# 3. Render ရဲ့ အခမဲ့ CPU Server ပေါ်တွင် ONNX / GPU အမှားမတက်စေရန် CPU ကိုသာ သုံးခိုင်းခြင်း
ENV ONNXRUNTIME_PROVIDERS=CPUExecutionProvider

# 4. စနစ်သစ်များတွင် Render အမှားမတက်စေရန် လိုအပ်သော Linux Packages များ ထည့်သွင်းခြင်း
RUN apt-get update && apt-get install -y \
    libgl1 \
    libglx-mesa0 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# 5. လိုအပ်သော package စာရင်းများကို ကူးယူပြီး install လုပ်ခြင်း
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 6. Project အတွင်းရှိ ဖိုင်အားလုံးကို Container ထဲ ကူးထည့်ခြင်း
COPY . .

# 7. Render အတွက် Port ဖွင့်ပေးခြင်း
EXPOSE 10000

# 8. သင့်ရဲ့ ပင်မ Python ဖိုင် (bot.py) ကို စတင်ပတ်မည့် Command
CMD ["python", "bot.py"]
