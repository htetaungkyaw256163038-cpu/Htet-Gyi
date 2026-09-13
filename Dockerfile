FROM python:3.10-slim
WORKDIR /app

# ONNX Runtime ကို CPU အတွက်သာ အလုပ်လုပ်စေပြီး အပို log များကို ပိတ်ထားခြင်း
ENV ONNXRUNTIME_PROVIDERS=CPUExecutionProvider
ENV ORT_Logging_Level=4

RUN apt-get update && apt-get install -y \
    libgl1 \
    libglx-mesa0 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
EXPOSE 10000
CMD ["python", "bot.py"]
