FROM python:3.11-slim
WORKDIR /srv
COPY services/retrieval/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY services/retrieval/ .
COPY shared /srv/shared
EXPOSE 8002
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8002"]
