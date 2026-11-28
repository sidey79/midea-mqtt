FROM python:3.15-slim@sha256:08a4c22c92b79ec821a7ad49768480039ee5b7accac3955228e75366e30abc8e AS builder

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --target /deps -r requirements.txt

FROM gcr.io/distroless/python3-debian13@sha256:7fa0d47901299aa0017c9ef24b8306f72567889977242dce2316b5cb81a06a1f

ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/deps

COPY --from=builder /deps /deps
COPY midea_mqtt_bridge.py /app/midea_mqtt_bridge.py

ENTRYPOINT ["python3", "/app/midea_mqtt_bridge.py"]
