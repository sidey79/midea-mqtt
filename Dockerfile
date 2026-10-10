FROM python:3.13-slim@sha256:70729b46c69b4f1e97c4822c1af3df53a1476cf5ddc6c087c0c10bc3a5678c2f AS builder

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --target /deps -r requirements.txt

FROM gcr.io/distroless/python3-debian13@sha256:e866e2f9fbaa19f63e579cf2f61b7f76cd8a74c43a62a0af95d48678d9878436

ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/deps

COPY --from=builder /deps /deps
COPY midea_mqtt_bridge.py /app/midea_mqtt_bridge.py

ENTRYPOINT ["python3", "/app/midea_mqtt_bridge.py"]
