FROM python:3.13-slim@sha256:57b29a7c050c4e679e4bea572e14b3965cf4b5839de2da49d55e49ffc4024f39 AS builder

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --target /deps -r requirements.txt

FROM gcr.io/distroless/python3-debian13@sha256:96234eaf03bba491856ead9142eccdda8cf9d09ce418770a260b84f529d81848

ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/deps

COPY --from=builder /deps /deps
COPY midea_mqtt_bridge.py /app/midea_mqtt_bridge.py

ENTRYPOINT ["python3", "/app/midea_mqtt_bridge.py"]
