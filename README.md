# midea-mqtt-bridge

Standalone repository for running the Midea / PortaSplit MQTT bridge.
The repo includes FHEM MQTT2 examples, but the bridge itself can be used with any MQTT consumer.

## Layout

- `Dockerfile`: container build for the bridge
- `midea_mqtt_bridge.py`: MQTT bridge entrypoint
- `docker-compose.yml`: minimal bridge service and internal network
- `examples/fhem-mqtt2-device.txt`: FHEM `MQTT2_DEVICE` example
- `test_midea_mqtt_bridge.py`: unit tests

## Quick Start

1. Copy `.env.example` to `.env` and fill in the values.
2. For the first device discovery run, start the bridge with the discovery override so the discovery traffic can reach the AC directly.
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.discovery.yml up -d
   ```
3. Once discovery has succeeded, store the discovered `MIDEA_AC_ID`, `MIDEA_AC_TOKEN`, and `MIDEA_AC_KEY` in `.env`. The token/key pair is what the bridge uses later to authenticate directly against the AC without repeating discovery.
4. Start the normal stack on the internal Docker network.
   ```bash
   docker compose up -d
   ```
5. Import the FHEM example from `examples/fhem-mqtt2-device.txt` if you use FHEM as the MQTT client.

## Environment

Required:
- `MIDEA_AC_HOST`
- `MIDEA_AC_TOKEN`
- `MIDEA_AC_KEY`

Optional:
- `MIDEA_AC_ID`
- `MIDEA_AC_PORT` default `6444`
- `MIDEA_POLL_INTERVAL` default `30`
- `MIDEA_TOPIC_BASE` default `midea/klima`
- `MQTT_HOST` default `fhem`
- `MQTT_PORT` default `1883`
- `MQTT_USER`
- `MQTT_PASSWORD`
- `LOG_LEVEL` default `INFO`

## Networking

- The bridge container and FHEM should share the same internal Docker network.
- This repository uses the `midea-mqtt-internal` network for the bridge.
- If your FHEM service uses a different container name, update `MQTT_HOST` accordingly.

## Notes

- The bridge publishes to `midea/klima` by default. Change `MIDEA_TOPIC_BASE` if you want a different topic prefix.
- FHEM is documented here as an example consumer, not as the only supported target.
- Adjust the FHEM topic base and room names to match your setup.
