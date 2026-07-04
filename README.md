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

1. Copy `.env.example` to `.env` or put the values directly into your stack file, whichever matches your deployment style.
2. Set `MIDEA_AC_HOST` before the first discovery run. The discovery override switches the container to a one-shot CLI mode and keeps the output on the console, so start it without `-d`.
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.discovery.yml up
   ```
3. Read the discovery result from the console output and copy `id`, plus `token`, `key`, and the discovered `port` when they are present, into `.env` or your stack file.
4. Stop the discovery stack if Compose is still attached, then start the normal bridge stack.
   ```bash
   docker compose up -d
   ```
5. Import the FHEM example from `examples/fhem-mqtt2-device.txt` if you use FHEM as the MQTT client.

## Discovery Example

Start discovery in the foreground so the JSON result stays visible in the terminal:

```bash
docker compose -f docker-compose.yml -f docker-compose.discovery.yml up
```

Example console output with redacted credentials:

```json
{
  "discovery_complete": true,
  "host": "192.0.2.55",
  "id": 123456789012345,
  "ip": "192.0.2.55",
  "key": "REDACTED_KEY",
  "port": 6445,
  "supported": true,
  "token": "REDACTED_TOKEN"
}
```

Use these values for the normal bridge run. Older or non-V3 devices may omit `token` and `key` in discovery output:

```env
MIDEA_AC_HOST=192.0.2.55
MIDEA_AC_PORT=6445
MIDEA_AC_ID=123456789012345
MIDEA_AC_TOKEN=REDACTED_TOKEN
MIDEA_AC_KEY=REDACTED_KEY
```

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
- `msmart-ng` 2026.7 adds Fresh Air support. The bridge uses `flash` as the canonical name and keeps `flash_cool` as a legacy compatibility alias.
- Supported values depend on the concrete AC model.
