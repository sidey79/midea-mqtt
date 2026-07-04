#!/usr/bin/env python3
import argparse
import asyncio
import json
import logging
import os
import signal
import time
from typing import Any

import paho.mqtt.client as mqtt
from msmart.device import AirConditioner as AC
from msmart.discover import Discover


LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
MQTT_HOST = os.getenv("MQTT_HOST", "fhem")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USER = os.getenv("MQTT_USER")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD")
MQTT_CLIENT_ID = os.getenv("MQTT_CLIENT_ID", "midea_bridge")
TOPIC_BASE = os.getenv("MIDEA_TOPIC_BASE", "midea/klima").strip("/")
STATE_TOPIC = f"{TOPIC_BASE}/state"
SET_TOPIC = f"{TOPIC_BASE}/set"
AVAILABILITY_TOPIC = f"{TOPIC_BASE}/availability"
POLL_INTERVAL = int(os.getenv("MIDEA_POLL_INTERVAL", "30"))
MQTT_CONNECT_RETRY_SECONDS = int(os.getenv("MQTT_CONNECT_RETRY_SECONDS", "5"))
DEVICE_RETRY_BASE_SECONDS = int(os.getenv("MIDEA_RETRY_BASE_SECONDS", str(max(POLL_INTERVAL, 30))))
DEVICE_RETRY_MAX_SECONDS = int(os.getenv("MIDEA_RETRY_MAX_SECONDS", "300"))

DEVICE_HOST = os.getenv("MIDEA_AC_HOST")
DEVICE_PORT = int(os.getenv("MIDEA_AC_PORT", "6444"))
DEVICE_ID = os.getenv("MIDEA_AC_ID")
DEVICE_TOKEN = os.getenv("MIDEA_AC_TOKEN")
DEVICE_KEY = os.getenv("MIDEA_AC_KEY")

LOGGER = logging.getLogger("midea-mqtt-bridge")


class DeviceUnavailableError(RuntimeError):
    pass


def enum_value(value: Any) -> Any:
    if hasattr(value, "name"):
        return value.name.lower()
    return value


def enum_values(values: Any) -> Any:
    if values is None:
        return None
    return [enum_value(value) for value in values]


def read_device_attr(device: Any, *attrs: str, default: Any = None) -> Any:
    for attr in attrs:
        value = getattr(device, attr, None)
        if value is not None:
            return value
    return default


def read_metric_value(device: Any, *attrs: str, default: Any = None) -> Any:
    for attr in attrs:
        value = getattr(device, attr, None)
        if value is None:
            continue
        if isinstance(value, dict):
            for item in value.values():
                if item is not None:
                    return item
            continue
        return value
    return default


def bool_power(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "on", "yes"}


def enum_from_input(enum_cls: Any, value: Any) -> Any:
    if isinstance(value, enum_cls):
        return value

    if isinstance(value, str):
        raw = value.strip()
        candidates = [raw]
        if "," in raw:
            candidates.extend(part.strip() for part in raw.split(","))
        for candidate in candidates:
            normalized = candidate.replace("-", "_").replace(" ", "_").upper()
            if hasattr(enum_cls, normalized):
                return getattr(enum_cls, normalized)
            for member in enum_cls:
                if str(member.value) == candidate:
                    return member
        try:
            numeric_value = int(raw)
        except ValueError:
            try:
                numeric_value = float(raw)
            except ValueError:
                numeric_value = None
        if numeric_value is not None:
            for member in enum_cls:
                if member.value == numeric_value:
                    return member
    else:
        for member in enum_cls:
            if member.value == value:
                return member

    raise AttributeError(
        f"type object '{enum_cls.__name__}' has no attribute '{str(value).replace('-', '_').upper()}'"
    )


def optional_bool(device: Any, *attrs: str) -> bool | None:
    for attr in attrs:
        value = getattr(device, attr, None)
        if value is not None:
            return bool(value)
    return None


def breeze_mode(device: Any) -> Any:
    value = read_device_attr(device, "breeze_mode", "_breeze_mode")
    return enum_value(value)


def breeze_flag(device: Any, expected: str) -> bool | None:
    value = read_device_attr(device, "breeze_mode", "_breeze_mode")
    if value is None:
        return None
    return enum_value(value) == expected


def set_device_attr(device: Any, value: Any, *attrs: str) -> bool:
    for attr in attrs:
        if hasattr(device, attr):
            setattr(device, attr, value)
            return True
    LOGGER.warning("Ignoring unsupported command field: %s", "/".join(attrs))
    return False


def set_optional_bool(device: Any, value: Any, *attrs: str) -> bool:
    return set_device_attr(device, bool_power(value), *attrs)


def set_optional_number(device: Any, value: Any, *attrs: str) -> bool:
    for converter in (int, float):
        try:
            parsed = converter(value)
            return set_device_attr(device, parsed, *attrs)
        except (TypeError, ValueError):
            continue
    LOGGER.warning("Ignoring unsupported command field: %s", "/".join(attrs))
    return False


def set_optional_enum(device: Any, enum_cls: Any, value: Any, *attrs: str) -> bool:
    try:
        parsed = enum_from_input(enum_cls, value)
    except Exception:
        LOGGER.exception("Ignoring invalid enum value for %s: %r", "/".join(attrs), value)
        return False
    return set_device_attr(device, parsed, *attrs)


def normalize_command_values(command: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(command)
    for key in ("target_temperature", "desired-temp"):
        if key in normalized:
            normalized[key] = float(normalized[key])
    enum_fields: dict[str, Any] = {
        "mode": getattr(AC, "OperationalMode", None),
        "operational_mode": getattr(AC, "OperationalMode", None),
        "fan": getattr(AC, "FanSpeed", None),
        "fan_speed": getattr(AC, "FanSpeed", None),
        "swing": getattr(AC, "SwingMode", None),
        "swing_mode": getattr(AC, "SwingMode", None),
        "cascade_mode": getattr(AC, "CascadeMode", None),
        "rate_select": getattr(AC, "RateSelect", None),
        "aux_mode": getattr(AC, "AuxHeatMode", None),
        "horizontal_swing_angle": getattr(AC, "SwingAngle", None),
        "vertical_swing_angle": getattr(AC, "SwingAngle", None),
        "breeze_mode": getattr(AC, "BreezeMode", None),
        "fresh_air_fan_speed": getattr(AC, "FreshAirFanSpeed", None),
    }
    for key, enum_cls in enum_fields.items():
        if key in normalized and enum_cls is not None:
            normalized[key] = enum_from_input(enum_cls, normalized[key])
    return normalized


async def set_display_state(device: Any, value: Any) -> None:
    desired = bool_power(value)
    if not hasattr(device, "display_on") or not hasattr(device, "toggle_display"):
        LOGGER.warning("Ignoring unsupported command field: display_on")
        return
    if bool(getattr(device, "display_on")) != desired:
        await device.toggle_display()


def extract_discovery_payload(device: Any, host: str) -> dict[str, Any]:
    payload = {
        "host": host,
        "id": getattr(device, "id", None),
        "ip": getattr(device, "ip", None),
        "port": getattr(device, "port", None),
        "supported": bool(getattr(device, "supported", False)),
        "token": getattr(device, "token", None) or getattr(device, "_token", None),
        "key": getattr(device, "key", None) or getattr(device, "_key", None),
    }
    return {key: value for key, value in payload.items() if value is not None}


class MideaBridge:
    def __init__(self) -> None:
        if not DEVICE_HOST:
            raise RuntimeError("MIDEA_AC_HOST is required")
        self.device: AC | None = None
        self.energy_estimate_wh = 0.0
        self.energy_estimate_at: float | None = None
        self.energy_estimate_power_w: float | None = None
        self.device_retry_at = 0.0
        self.device_retry_delay = DEVICE_RETRY_BASE_SECONDS
        self.device_offline_published = False
        self.commands: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self.device_lock = asyncio.Lock()
        self.stop_event = asyncio.Event()
        self.loop = asyncio.get_running_loop()
        self.mqtt = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=MQTT_CLIENT_ID,
        )
        if MQTT_USER:
            self.mqtt.username_pw_set(MQTT_USER, MQTT_PASSWORD)
        self.mqtt.will_set(AVAILABILITY_TOPIC, "offline", retain=True)
        self.mqtt.on_connect = self.on_connect
        self.mqtt.on_message = self.on_message

    def on_connect(self, client: mqtt.Client, _userdata: Any, _flags: Any, reason_code: Any, _properties: Any) -> None:
        if reason_code == 0:
            LOGGER.info("Connected to MQTT broker %s:%s", MQTT_HOST, MQTT_PORT)
            client.subscribe(SET_TOPIC)
            client.publish(AVAILABILITY_TOPIC, "online", retain=True)
        else:
            LOGGER.error("MQTT connection failed: %s", reason_code)

    def on_message(self, _client: mqtt.Client, _userdata: Any, message: mqtt.MQTTMessage) -> None:
        try:
            payload = message.payload.decode("utf-8")
            command = json.loads(payload)
            if not isinstance(command, dict):
                raise ValueError("command payload must be a JSON object")
            self.loop.call_soon_threadsafe(self.commands.put_nowait, command)
        except Exception:
            LOGGER.exception("Ignoring invalid command on %s: %r", message.topic, message.payload)

    def publish_unavailable_state(self, error: str) -> None:
        if self.device_offline_published:
            return
        self.mqtt.publish(
            STATE_TOPIC,
            json.dumps({"online": False, "error": error, "last_update": int(time.time())}),
            retain=True,
        )
        self.device_offline_published = True

    def mark_device_offline(self, reason: Exception | None = None) -> None:
        delay = self.device_retry_delay
        self.device = None
        self.energy_estimate_at = None
        self.energy_estimate_power_w = None
        self.device_retry_at = time.monotonic() + delay
        self.device_retry_delay = min(delay * 2, DEVICE_RETRY_MAX_SECONDS)
        if reason is None:
            LOGGER.warning("Midea AC unavailable; retrying in %ss", delay)
        else:
            LOGGER.warning("Midea AC unavailable; retrying in %ss: %s", delay, reason)

    def mark_device_online(self) -> None:
        self.device_retry_at = 0.0
        self.device_retry_delay = DEVICE_RETRY_BASE_SECONDS
        self.device_offline_published = False

    def update_energy_estimate(self, device: AC) -> dict[str, Any] | None:
        power_value = read_metric_value(device, "real_time_power", "_real_time_power_usage")
        if power_value is None:
            return None
        try:
            power_w = float(power_value)
        except (TypeError, ValueError):
            LOGGER.warning("Ignoring non-numeric real_time_power value: %r", power_value)
            return None

        now = time.monotonic()
        if self.energy_estimate_at is not None and self.energy_estimate_power_w is not None:
            elapsed_hours = max(0.0, now - self.energy_estimate_at) / 3600.0
            self.energy_estimate_wh += self.energy_estimate_power_w * elapsed_hours

        self.energy_estimate_at = now
        self.energy_estimate_power_w = power_w
        return {
            "estimated_energy_wh": round(self.energy_estimate_wh, 3),
            "estimated_energy_kwh": round(self.energy_estimate_wh / 1000.0, 6),
        }

    async def connect_device(self) -> AC:
        if DEVICE_ID:
            device = AC(ip=DEVICE_HOST, port=DEVICE_PORT, device_id=int(DEVICE_ID))
            if DEVICE_TOKEN and DEVICE_KEY:
                await device.authenticate(DEVICE_TOKEN, DEVICE_KEY)
        else:
            discovered = await Discover.discover_single(DEVICE_HOST)
            if not isinstance(discovered, AC):
                raise RuntimeError(f"Discovered device at {DEVICE_HOST} is not a supported air conditioner")
            device = discovered
            discovered_token = getattr(device, "token", None) or getattr(device, "_token", None)
            discovered_key = getattr(device, "key", None) or getattr(device, "_key", None)
            if not discovered_token or not discovered_key:
                raise RuntimeError(
                    "Discovery succeeded, but token/key were not provided by the library. "
                    "Use --discover-output console|mqtt|both to inspect the device and feed the values back in. "
                    "Set MIDEA_AC_TOKEN and MIDEA_AC_KEY before starting the bridge."
                )
        await device.get_capabilities()
        await self.enable_optional_telemetry(device)
        await device.refresh()
        LOGGER.info("Connected to Midea AC id=%s ip=%s supported=%s", device.id, device.ip, device.supported)
        self.device = device
        self.mark_device_online()
        return device

    async def enable_optional_telemetry(self, device: AC) -> None:
        for attr_name in ("enable_energy_usage_requests", "enable_group5_data_requests"):
            if not hasattr(device, attr_name):
                continue
            try:
                setattr(device, attr_name, True)
                LOGGER.info("Enabled %s on Midea AC", attr_name)
            except Exception:
                LOGGER.exception("Failed to enable %s on Midea AC", attr_name)

    async def get_device(self) -> AC:
        if self.device is None:
            if time.monotonic() < self.device_retry_at:
                raise DeviceUnavailableError("Midea AC is temporarily offline")
            return await self.connect_device()
        return self.device

    def state_payload(self, device: AC, estimated_energy: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = {
            "id": getattr(device, "id", None),
            "ip": getattr(device, "ip", None),
            "online": bool(getattr(device, "online", False)),
            "supported": bool(getattr(device, "supported", False)),
            "power": "on" if getattr(device, "power_state", False) else "off",
            "power_state": bool(getattr(device, "power_state", False)),
            "desired-temp": getattr(device, "target_temperature", None),
            "target_temperature": getattr(device, "target_temperature", None),
            "measured-temp": getattr(device, "indoor_temperature", None),
            "indoor_temperature": getattr(device, "indoor_temperature", None),
            "indoor_humidity": read_device_attr(device, "indoor_humidity", "_indoor_humidity"),
            "outdoor_temperature": getattr(device, "outdoor_temperature", None),
            "error_code": read_device_attr(device, "error_code", "_error_code"),
            "self_clean_active": read_device_attr(device, "self_clean_active", "_self_clean_active"),
            "defrost_active": read_device_attr(device, "defrost_active", "_defrost_active"),
            "outdoor_fan_speed": read_device_attr(device, "outdoor_fan_speed", "_outdoor_fan_speed"),
            "total_energy": read_metric_value(device, "total_energy", "_total_energy_usage"),
            "current_energy": read_metric_value(device, "current_energy", "_current_energy_usage"),
            "real_time_power": read_metric_value(device, "real_time_power", "_real_time_power_usage"),
            "mode": enum_value(getattr(device, "operational_mode", None)),
            "fan": enum_value(getattr(device, "fan_speed", None)),
            "swing": enum_value(getattr(device, "swing_mode", None)),
            "supported_operation_modes": enum_values(read_device_attr(device, "supported_operation_modes", "_supported_op_modes")),
            "supported_fan_speeds": enum_values(read_device_attr(device, "supported_fan_speeds", "_supported_fan_speeds")),
            "supported_swing_modes": enum_values(read_device_attr(device, "supported_swing_modes", "_supported_swing_modes")),
            "supported_aux_modes": enum_values(read_device_attr(device, "supported_aux_modes", "_supported_aux_modes")),
            "supported_rate_selects": enum_values(read_device_attr(device, "supported_rate_selects", "_supported_rate_selects")),
            "eco": optional_bool(device, "eco", "eco_mode"),
            "eco_mode": optional_bool(device, "eco", "eco_mode"),
            "freeze_protection": optional_bool(device, "freeze_protection", "_freeze_protection"),
            "sleep": optional_bool(device, "sleep", "_sleep"),
            "follow_me": optional_bool(device, "follow_me", "_follow_me"),
            "purifier": optional_bool(device, "purifier", "_purifier"),
            "ieco": optional_bool(device, "ieco", "_ieco"),
            "flash": optional_bool(device, "flash", "_flash", "flash_cool", "_flash_cool"),
            "flash_cool": optional_bool(device, "flash_cool", "_flash_cool", "flash", "_flash"),
            "fresh_air_fan_speed": enum_value(
                read_device_attr(device, "fresh_air_fan_speed", "_fresh_air_fan_speed")
            ),
            "supports_flash": optional_bool(device, "supports_flash", "supports_flash_cool"),
            "supports_fresh_air": optional_bool(device, "supports_fresh_air"),
            "out_silent": optional_bool(device, "out_silent", "_out_silent"),
            "turbo": optional_bool(device, "turbo", "turbo_mode"),
            "turbo_mode": optional_bool(device, "turbo", "turbo_mode"),
            "display_on": optional_bool(device, "display_on"),
            "fahrenheit": optional_bool(device, "fahrenheit"),
            "filter_alert": optional_bool(device, "filter_alert", "_filter_alert"),
            "target_humidity": read_device_attr(device, "target_humidity", "_target_humidity"),
            "cascade_mode": enum_value(read_device_attr(device, "cascade_mode", "_cascade_mode")),
            "rate_select": enum_value(read_device_attr(device, "rate_select", "_rate_select")),
            "aux_mode": enum_value(read_device_attr(device, "aux_mode", "_aux_mode")),
            "breeze_mode": breeze_mode(device),
            "breeze_away": breeze_flag(device, "breeze_away"),
            "breeze_mild": breeze_flag(device, "breeze_mild"),
            "breezeless": breeze_flag(device, "breezeless"),
            "horizontal_swing_angle": enum_value(read_device_attr(device, "horizontal_swing_angle", "_horizontal_swing_angle")),
            "vertical_swing_angle": enum_value(read_device_attr(device, "vertical_swing_angle", "_vertical_swing_angle")),
            "last_update": int(time.time()),
        }
        if estimated_energy is not None:
            payload.update(estimated_energy)
        return {key: value for key, value in payload.items() if value is not None}

    async def publish_state(self) -> None:
        try:
            async with self.device_lock:
                device = await self.get_device()
                await device.refresh()
                if not bool(getattr(device, "online", True)):
                    self.mark_device_offline(RuntimeError("device reported offline"))
                    self.publish_unavailable_state("poll_failed")
                    return
                self.mark_device_online()
                estimated_energy = self.update_energy_estimate(device)
                payload = self.state_payload(device, estimated_energy)
        except DeviceUnavailableError:
            self.publish_unavailable_state("poll_failed")
            return
        except Exception as exc:
            self.mark_device_offline(exc)
            self.publish_unavailable_state("poll_failed")
            return
        self.mqtt.publish(STATE_TOPIC, json.dumps(payload, separators=(",", ":")), retain=True)

    async def apply_command(self, command: dict[str, Any]) -> None:
        try:
            command = normalize_command_values(command)
        except (AttributeError, TypeError, ValueError) as exc:
            LOGGER.warning("Ignoring invalid command value: %r (%s)", command, exc)
            return
        try:
            async with self.device_lock:
                device = await self.get_device()
                await device.refresh()
                LOGGER.info("Applying command: %s", command)
                if "power" in command:
                    device.power_state = bool_power(command["power"])
                if "power_state" in command:
                    device.power_state = bool_power(command["power_state"])
                if "target_temperature" in command:
                    device.target_temperature = command["target_temperature"]
                if "desired-temp" in command:
                    device.target_temperature = command["desired-temp"]
                if "mode" in command:
                    device.operational_mode = command["mode"]
                if "operational_mode" in command:
                    device.operational_mode = command["operational_mode"]
                if "fan" in command:
                    device.fan_speed = command["fan"]
                if "fan_speed" in command:
                    device.fan_speed = command["fan_speed"]
                if "swing" in command:
                    device.swing_mode = command["swing"]
                if "swing_mode" in command:
                    device.swing_mode = command["swing_mode"]
                if "cascade_mode" in command:
                    set_device_attr(device, command["cascade_mode"], "cascade_mode", "_cascade_mode")
                if "rate_select" in command:
                    set_device_attr(device, command["rate_select"], "rate_select", "_rate_select")
                if "aux_mode" in command:
                    set_device_attr(device, command["aux_mode"], "aux_mode", "_aux_mode")
                if "horizontal_swing_angle" in command:
                    set_device_attr(device, command["horizontal_swing_angle"], "horizontal_swing_angle", "_horizontal_swing_angle")
                if "vertical_swing_angle" in command:
                    set_device_attr(device, command["vertical_swing_angle"], "vertical_swing_angle", "_vertical_swing_angle")
                display_command = None
                if "display_on" in command:
                    display_command = command["display_on"]
                if "beep" in command:
                    set_optional_bool(device, command["beep"], "beep", "beep_on")
                if "eco" in command:
                    set_optional_bool(device, command["eco"], "eco", "eco_mode")
                if "eco_mode" in command:
                    set_optional_bool(device, command["eco_mode"], "eco", "eco_mode")
                if "freeze_protection" in command:
                    set_optional_bool(device, command["freeze_protection"], "freeze_protection", "_freeze_protection")
                if "sleep" in command:
                    set_optional_bool(device, command["sleep"], "sleep", "_sleep")
                if "follow_me" in command:
                    set_optional_bool(device, command["follow_me"], "follow_me", "_follow_me")
                if "purifier" in command:
                    set_optional_bool(device, command["purifier"], "purifier", "_purifier")
                if "ieco" in command:
                    set_optional_bool(device, command["ieco"], "ieco", "_ieco")
                if "flash" in command:
                    set_optional_bool(device, command["flash"], "flash", "flash_cool")
                if "flash_cool" in command:
                    set_optional_bool(device, command["flash_cool"], "flash", "flash_cool")
                if "out_silent" in command:
                    set_optional_bool(device, command["out_silent"], "out_silent", "_out_silent")
                if "target_humidity" in command:
                    set_optional_number(device, command["target_humidity"], "target_humidity", "_target_humidity")
                if "fresh_air_fan_speed" in command:
                    set_device_attr(
                        device,
                        command["fresh_air_fan_speed"],
                        "fresh_air_fan_speed",
                        "_fresh_air_fan_speed",
                    )
                if "turbo" in command:
                    set_optional_bool(device, command["turbo"], "turbo", "turbo_mode")
                if "turbo_mode" in command:
                    set_optional_bool(device, command["turbo_mode"], "turbo", "turbo_mode")
                if "breeze_mode" in command:
                    breeze = command["breeze_mode"]
                    if breeze == AC.BreezeMode.BREEZE_AWAY:
                        set_optional_bool(device, True, "breeze_away")
                    elif breeze == AC.BreezeMode.BREEZE_MILD:
                        set_optional_bool(device, True, "breeze_mild")
                    elif breeze == AC.BreezeMode.BREEZELESS:
                        set_optional_bool(device, True, "breezeless")
                    else:
                        set_optional_bool(device, False, "breeze_away")
                        set_optional_bool(device, False, "breeze_mild")
                        set_optional_bool(device, False, "breezeless")
                if "breeze_away" in command:
                    set_optional_bool(device, command["breeze_away"], "breeze_away")
                if "breeze_mild" in command:
                    set_optional_bool(device, command["breeze_mild"], "breeze_mild")
                if "breezeless" in command:
                    set_optional_bool(device, command["breezeless"], "breezeless")
                if "self_clean" in command:
                    if bool_power(command["self_clean"]):
                        if hasattr(device, "start_self_clean"):
                            await device.start_self_clean()
                        else:
                            LOGGER.warning("Ignoring unsupported command field: self_clean")
                await device.apply()
                if display_command is not None:
                    await set_display_state(device, display_command)
        except DeviceUnavailableError:
            self.publish_unavailable_state("command_failed")
            return
        except Exception as exc:
            self.mark_device_offline(exc)
            self.publish_unavailable_state("command_failed")
            return
        await self.publish_state()

    async def command_worker(self) -> None:
        while not self.stop_event.is_set():
            command = await self.commands.get()
            try:
                await self.apply_command(command)
            except Exception:
                LOGGER.exception("Command worker failed while applying command: %r", command)

    async def poll_worker(self) -> None:
        while not self.stop_event.is_set():
            await self.publish_state()
            sleep_for = POLL_INTERVAL
            if self.device is None:
                remaining = self.device_retry_at - time.monotonic()
                if remaining > sleep_for:
                    sleep_for = remaining
            await asyncio.sleep(sleep_for)

    async def connect_mqtt(self) -> None:
        while not self.stop_event.is_set():
            try:
                self.mqtt.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
                return
            except OSError:
                LOGGER.exception(
                    "MQTT broker %s:%s is not reachable; retrying in %ss",
                    MQTT_HOST,
                    MQTT_PORT,
                    MQTT_CONNECT_RETRY_SECONDS,
                )
                await asyncio.sleep(MQTT_CONNECT_RETRY_SECONDS)

    async def run(self) -> None:
        await self.connect_mqtt()
        if self.stop_event.is_set():
            return
        self.mqtt.loop_start()
        worker = asyncio.create_task(self.command_worker())
        poller = asyncio.create_task(self.poll_worker())
        try:
            await self.stop_event.wait()
        finally:
            worker.cancel()
            poller.cancel()
            self.mqtt.publish(AVAILABILITY_TOPIC, "offline", retain=True)
            self.mqtt.loop_stop()
            self.mqtt.disconnect()


async def run_discovery(output: str) -> int:
    if not DEVICE_HOST:
        raise RuntimeError("MIDEA_AC_HOST is required for discovery")
    discovered = await Discover.discover_single(DEVICE_HOST)
    if not isinstance(discovered, AC):
        raise RuntimeError(f"Discovered device at {DEVICE_HOST} is not a supported air conditioner")
    payload = extract_discovery_payload(discovered, DEVICE_HOST)
    payload["discovery_complete"] = True
    payload_json = json.dumps(payload, indent=2, sort_keys=True)
    if output in {"console", "both"}:
        print(payload_json)
    if output in {"mqtt", "both"}:
        bridge = MideaBridge()
        bridge.mqtt.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
        bridge.mqtt.loop_start()
        try:
            bridge.mqtt.publish(STATE_TOPIC, payload_json, retain=True)
            bridge.mqtt.publish(AVAILABILITY_TOPIC, "online", retain=True)
        finally:
            bridge.mqtt.loop_stop()
            bridge.mqtt.disconnect()
    if not payload.get("token") or not payload.get("key"):
        LOGGER.error("Discovery completed, but token/key were not found in the device object")
        return 2
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Midea MQTT bridge")
    parser.add_argument("--discover", action="store_true", help="run discovery and exit")
    parser.add_argument(
        "--discover-output",
        choices=("console", "mqtt", "both"),
        default="console",
        help="where to publish discovery results",
    )
    return parser.parse_args(argv)


async def main() -> int:
    logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    args = parse_args()
    if args.discover:
        return await run_discovery(args.discover_output)
    bridge = MideaBridge()
    loop = asyncio.get_running_loop()
    for signame in ("SIGINT", "SIGTERM"):
        loop.add_signal_handler(getattr(signal, signame), bridge.stop_event.set)
    await bridge.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
