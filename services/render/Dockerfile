# invest-nyawit render service — ffmpeg + edge-tts
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY render.py .

EXPOSE 8090
CMD ["python", "render.py", "--serve", "--port", "8090", "--media", "/media"]
