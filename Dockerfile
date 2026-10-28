FROM python:3.15-slim@sha256:94d3426f1def7db4a106a232ac121bfd975393e5dfd40a619b955fae45fe7913 AS builder

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --target /deps -r requirements.txt

FROM gcr.io/distroless/python3-debian13@sha256:0db804f397ca31a1498c9d94c3c1df53fe49ac8007e5942b1cb547c1c3355c09

ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/deps

COPY --from=builder /deps /deps
COPY midea_mqtt_bridge.py /app/midea_mqtt_bridge.py

ENTRYPOINT ["python3", "/app/midea_mqtt_bridge.py"]
