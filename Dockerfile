FROM python:3.13-slim@sha256:09a17cad02668ae61ece136b4fd36ac3849e14f670ebedb637ea3e15580525bc AS builder

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --target /deps -r requirements.txt

FROM gcr.io/distroless/python3-debian13@sha256:9a1ed29d41d7695245ff86bc2e08684d3dd253a3f9c8ca45677427f9f4fe3598

ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/deps

COPY --from=builder /deps /deps
COPY midea_mqtt_bridge.py /app/midea_mqtt_bridge.py

ENTRYPOINT ["python3", "/app/midea_mqtt_bridge.py"]
