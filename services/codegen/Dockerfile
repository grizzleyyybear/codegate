FROM python:3.11-slim
WORKDIR /srv
COPY services/codegen/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY services/codegen/ .
COPY shared /srv/shared
EXPOSE 8003
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8003"]
