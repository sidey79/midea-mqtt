# midea-fhem-bridge-example

Standalone repository for running the Midea / PortaSplit MQTT bridge with FHEM.

## Layout

- `Dockerfile`: container build for the bridge
- `midea_mqtt_bridge.py`: MQTT bridge entrypoint
- `docker-compose.yml`: minimal bridge service
- `examples/fhem-mqtt2-device.txt`: portable FHEM `MQTT2_DEVICE` example
- `test_midea_mqtt_bridge.py`: unit tests

## Quick Start

1. Copy `.env.example` to `.env` and fill in the values.
2. Start the bridge.
   ```bash
   docker compose up -d
   ```
3. Import the FHEM example from `examples/fhem-mqtt2-device.txt`.

## Environment

Required:
- `MIDEA_AC_HOST`
- `MIDEA_AC_TOKEN`
- `MIDEA_AC_KEY`

Optional:
- `MIDEA_AC_ID`
- `MIDEA_AC_PORT` default `6444`
- `MIDEA_POLL_INTERVAL` default `30`
- `MIDEA_TOPIC_BASE` default `midea/buero/klima`
- `MQTT_HOST` default `fhem`
- `MQTT_PORT` default `1883`
- `MQTT_USER`
- `MQTT_PASSWORD`
- `LOG_LEVEL` default `INFO`

## Notes

- The bridge publishes to `midea/buero/klima` by default. Change `MIDEA_TOPIC_BASE` if you want a different topic prefix.
- For discovery on some networks, `msmart-ng discover` works more reliably with host networking.
- The FHEM example is intentionally generic. Adjust the topic base and room names to match your setup.
