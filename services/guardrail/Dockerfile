FROM python:3.11-slim
WORKDIR /srv
COPY services/guardrail/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY services/guardrail/ .
COPY shared /srv/shared
EXPOSE 8005
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8005"]
