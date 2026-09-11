FROM python:3.10-slim

WORKDIR /app

# လိုအပ်သော Packages များကို သီးသန့် အရင်ထည့်သွင်းခြင်း
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "bot.py"]
