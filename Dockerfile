FROM python:3.10-slim

# ddddocr (onnxruntime) နှင့် OpenCV အတွက် လိုအပ်သော Linux Libraries များ ထည့်သွင်းခြင်း
RUN apt-get update && apt-get install -y \
    libgl1-mesa-glx \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "bot.py"]
