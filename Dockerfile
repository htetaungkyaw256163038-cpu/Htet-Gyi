# 1. Base Image အဖြစ် တရားဝင် Python Image ကို သုံးပါမည်
FROM python:3.10-slim

# 2. Container အတွင်း အလုပ်လုပ်မည့် Folder သတ်မှတ်ခြင်း
WORKDIR /app

# 3. ONNX Runtime ကို GPU လုံးဝမရှာဘဲ CPU သီးသန့်ပဲ သုံးဖို့ စနစ်တစ်ခုလုံးကို အမိန့်ပေးခြင်း
ENV ONNXRUNTIME_PROVIDERS=CPUExecutionProvider
ENV PIP_NO_CACHE_DIR=1

# 4. အခြေခံ packages များကို သွင်းခြင်း
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 5. ddddocr ဗားရှင်းမကိုက်ညီမှု မရှိစေရန် onnxruntime ပုံမှန်ကို သွင်းပြီး ddddocr ကို dependencies မပါဘဲ ခွဲသွင်းခြင်း
RUN pip install --no-cache-dir onnxruntime
RUN pip install --no-cache-dir ddddocr --no-dependencies

# 6. Project အတွင်းရှိ ဖိုင်အားလုံးကို Container ထဲ ကူးထည့်ခြင်း
COPY . .

# 7. Render အတွက် Port ဖွင့်ပေးခြင်း
EXPOSE 10000

# 8. Bot ကို စတင်ပတ်မည့် Command
CMD ["python", "bot.py"]
