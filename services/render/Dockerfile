# invest-nyawit render service — ffmpeg + edge-tts + BGM + karaoke
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg fonts-dejavu-core fonts-liberation \
        fontconfig curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# font asli (Poppins) supaya caption tidak fallback DejaVu
RUN mkdir -p /usr/share/fonts/truetype/poppins && \
    curl -sL -o /usr/share/fonts/truetype/poppins/Poppins-Bold.ttf "https://github.com/google/fonts/raw/main/ofl/poppins/Poppins-Bold.ttf" && \
    curl -sL -o /usr/share/fonts/truetype/poppins/Poppins-Regular.ttf "https://github.com/google/fonts/raw/main/ofl/poppins/Poppins-Regular.ttf" && \
    curl -sL -o /usr/share/fonts/truetype/poppins/Poppins-SemiBold.ttf "https://github.com/google/fonts/raw/main/ofl/poppins/Poppins-SemiBold.ttf" && \
    curl -sL -o /usr/share/fonts/truetype/poppins/Poppins-ExtraBold.ttf "https://github.com/google/fonts/raw/main/ofl/poppins/Poppins-ExtraBold.ttf" && \
    fc-cache -f

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY render.py .

EXPOSE 8090
CMD ["python", "render.py", "--serve", "--port", "8090", "--media", "/media"]
