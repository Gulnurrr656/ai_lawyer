FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . .

ENV APP_ENV=production
ENV WEB_BASE_URL=https://zangerpro.kz
ENV STORAGE_DIR=exports
ENV UPLOAD_DIR=var/uploads
ENV ZANGERPRO_DB_PATH=var/zangerpro.db

EXPOSE 8000

CMD ["uvicorn", "app.web.main:app", "--host", "0.0.0.0", "--port", "8000"]
