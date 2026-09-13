# 1. Base Image အဖြစ် Python ကို သုံးပါမည်
FROM python:3.10-slim

# 2. Container အတွင်း အလုပ်လုပ်မည့် Folder သတ်မှတ်ခြင်း
WORKDIR /app

# 3. စနစ်သစ်များတွင် Render အမှားမတက်စေရန် လိုအပ်သော Linux Packages များ ထည့်သွင်းခြင်း
RUN apt-get update && apt-get install -y \
    libgl1 \
    libglx-mesa0 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# 4. လိုအပ်သော package စာရင်းများကို ကူးယူပြီး install လုပ်ခြင်း
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 5. Project အတွင်းရှိ ဖိုင်အားလုံးကို Container ထဲ ကူးထည့်ခြင်း
COPY . .

# 6. Render အတွက် Port ဖွင့်ပေးခြင်း (သင့် App ပေါ်မူတည်၍ ပြောင်းလဲနိုင်သည်)
EXPOSE 10000

# 7. Application ကို စတင်ပတ်မည့် Command (ဥပမာ- uvicorn app:app သို့မဟုတ် python main.py)
CMD ["python", "main.py"]
