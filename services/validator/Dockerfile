FROM python:3.11-slim
WORKDIR /srv
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*
COPY services/validator/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY services/validator/ .
COPY shared /srv/shared
EXPOSE 8004
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8004"]
