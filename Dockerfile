FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py list_chats.py web.py ./
COPY templates ./templates
COPY static ./static

CMD ["python", "app.py"]
