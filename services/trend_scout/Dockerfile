# invest-nyawit trend scout — hanya stdlib, tanpa dependensi eksternal
FROM python:3.12-slim

WORKDIR /app
COPY trend_scout.py .

EXPOSE 8092
CMD ["python", "trend_scout.py", "--serve", "--port", "8092"]
