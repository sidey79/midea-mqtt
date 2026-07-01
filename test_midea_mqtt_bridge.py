import asyncio
import contextlib
import enum
import importlib
import sys
import types
import unittest
from pathlib import Path

MODULE_DIR = Path(__file__).resolve().parent
if str(MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(MODULE_DIR))


def install_dependency_stubs() -> None:
    if "paho.mqtt.client" not in sys.modules:
        paho_module = types.ModuleType("paho")
        mqtt_package = types.ModuleType("paho.mqtt")
        mqtt_module = types.ModuleType("paho.mqtt.client")
        paho_module.__path__ = []
        mqtt_package.__path__ = []

        class CallbackAPIVersion:
            VERSION2 = object()

        class Client:  # pragma: no cover - only used for import-time compatibility
            def __init__(self, *args, **kwargs):
                pass

        class MQTTMessage:  # pragma: no cover - only used for import-time compatibility
            pass

        mqtt_module.CallbackAPIVersion = CallbackAPIVersion
        mqtt_module.Client = Client
        mqtt_module.MQTTMessage = MQTTMessage
        mqtt_package.client = mqtt_module
        paho_module.mqtt = mqtt_package
        sys.modules["paho"] = paho_module
        sys.modules["paho.mqtt"] = mqtt_package
        sys.modules["paho.mqtt.client"] = mqtt_module

    if "msmart.device" not in sys.modules:
        msmart_module = types.ModuleType("msmart")
        device_module = types.ModuleType("msmart.device")
        discover_module = types.ModuleType("msmart.discover")
        msmart_module.__path__ = []

        class AirConditioner:  # pragma: no cover - only used for import-time compatibility
            pass

        class Discover:  # pragma: no cover - only used for import-time compatibility
            pass

        device_module.AirConditioner = AirConditioner
        discover_module.Discover = Discover
        msmart_module.device = device_module
        msmart_module.discover = discover_module
        sys.modules["msmart"] = msmart_module
        sys.modules["msmart.device"] = device_module
        sys.modules["msmart.discover"] = discover_module


install_dependency_stubs()
midea_mqtt_bridge = importlib.import_module("midea_mqtt_bridge")


class StatePayloadTests(unittest.TestCase):
    def test_state_payload_includes_energy_readings(self) -> None:
        bridge = object.__new__(midea_mqtt_bridge.MideaBridge)
        device = types.SimpleNamespace(
            id=123,
            ip="192.0.2.10",
            online=True,
            supported=True,
            power_state=True,
            target_temperature=21.5,
            indoor_temperature=22.0,
            indoor_humidity=48,
            outdoor_temperature=35.0,
            error_code=None,
            self_clean_active=False,
            defrost_active=False,
            outdoor_fan_speed=3,
            operational_mode=types.SimpleNamespace(name="COOL"),
            fan_speed=types.SimpleNamespace(name="AUTO"),
            swing_mode=types.SimpleNamespace(name="OFF"),
            supported_operation_modes=[types.SimpleNamespace(name="AUTO"), types.SimpleNamespace(name="COOL")],
            supported_fan_speeds=[types.SimpleNamespace(name="AUTO")],
            supported_swing_modes=[types.SimpleNamespace(name="OFF")],
            supported_aux_modes=[types.SimpleNamespace(name="OFF")],
            supported_rate_selects=[types.SimpleNamespace(name="OFF"), types.SimpleNamespace(name="GEAR_50")],
            eco_mode=False,
            turbo_mode=False,
            display_on=False,
            fahrenheit=False,
            filter_alert=False,
            target_humidity=40,
            cascade_mode=types.SimpleNamespace(name="OFF"),
            rate_select=types.SimpleNamespace(name="OFF"),
            aux_mode=types.SimpleNamespace(name="OFF"),
            breeze_mode=types.SimpleNamespace(name="OFF"),
            horizontal_swing_angle=types.SimpleNamespace(name="OFF"),
            vertical_swing_angle=types.SimpleNamespace(name="OFF"),
            _total_energy_usage={"bcd": 1234, "binary": None},
            _current_energy_usage={"bcd": 56, "binary": None},
            _real_time_power_usage={"bcd": 789, "binary": None},
        )

        payload = midea_mqtt_bridge.MideaBridge.state_payload(bridge, device)

        self.assertEqual(payload["total_energy"], 1234)
        self.assertEqual(payload["current_energy"], 56)
        self.assertEqual(payload["real_time_power"], 789)

    def test_state_payload_includes_estimated_energy(self) -> None:
        bridge = object.__new__(midea_mqtt_bridge.MideaBridge)
        bridge.energy_estimate_wh = 1234.567
        device = types.SimpleNamespace(online=True)

        payload = midea_mqtt_bridge.MideaBridge.state_payload(
            bridge,
            device,
            {"estimated_energy_wh": 1234.567, "estimated_energy_kwh": 1.234567},
        )

        self.assertEqual(payload["estimated_energy_wh"], 1234.567)
        self.assertEqual(payload["estimated_energy_kwh"], 1.234567)


class CommandWorkerTests(unittest.IsolatedAsyncioTestCase):
    async def test_command_worker_continues_after_apply_command_failure(self) -> None:
        bridge = object.__new__(midea_mqtt_bridge.MideaBridge)
        bridge.stop_event = asyncio.Event()
        bridge.commands = asyncio.Queue()

        seen_commands: list[dict[str, object]] = []

        async def fake_apply_command(command: dict[str, object]) -> None:
            seen_commands.append(command)
            if len(seen_commands) == 1:
                raise RuntimeError("boom")
            bridge.stop_event.set()

        bridge.apply_command = fake_apply_command

        await bridge.commands.put({"command": "first"})
        await bridge.commands.put({"command": "second"})

        worker = asyncio.create_task(bridge.command_worker())
        try:
            await asyncio.wait_for(bridge.stop_event.wait(), timeout=1)
            await asyncio.wait_for(worker, timeout=1)
        finally:
            if not worker.done():
                worker.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await worker

        self.assertEqual(seen_commands, [{"command": "first"}, {"command": "second"}])


class PollOfflineTests(unittest.IsolatedAsyncioTestCase):
    async def test_publish_state_marks_device_offline_when_refresh_reports_offline(self) -> None:
        bridge = object.__new__(midea_mqtt_bridge.MideaBridge)
        bridge.device_lock = asyncio.Lock()
        bridge.stop_event = asyncio.Event()
        bridge.device_offline_published = False
        bridge.device_retry_delay = 5
        bridge.device_retry_at = 0.0
        published: list[tuple[tuple[object, ...], dict[str, object]]] = []
        bridge.mqtt = types.SimpleNamespace(publish=lambda *args, **kwargs: published.append((args, kwargs)))

        device = types.SimpleNamespace(
            online=False,
            refresh=lambda: asyncio.sleep(0),
            id=1,
            ip="192.0.2.10",
            supported=True,
        )

        async def fake_get_device() -> types.SimpleNamespace:
            bridge.device = device
            return device

        bridge.get_device = fake_get_device

        await bridge.publish_state()

        self.assertIsNone(bridge.device)
        self.assertTrue(bridge.device_offline_published)
        self.assertEqual(len(published), 1)
        self.assertEqual(published[0][0][0], midea_mqtt_bridge.STATE_TOPIC)
        payload = published[0][0][1]
        self.assertIn('"online": false', payload)
        self.assertIn('"error": "poll_failed"', payload)


class CascadeModeCommandTests(unittest.IsolatedAsyncioTestCase):
    async def test_apply_command_sets_public_cascade_property(self) -> None:
        bridge = object.__new__(midea_mqtt_bridge.MideaBridge)
        bridge.device_lock = asyncio.Lock()
        bridge.stop_event = asyncio.Event()
        bridge.device_offline_published = False
        bridge.device_retry_delay = 5
        bridge.device_retry_at = 0.0
        bridge.mqtt = types.SimpleNamespace(publish=lambda *args, **kwargs: None)

        midea_mqtt_bridge.AC.CascadeMode = enum.Enum("CascadeMode", "OFF UP DOWN")

        device = types.SimpleNamespace(
            refresh=lambda: asyncio.sleep(0),
            apply=lambda: asyncio.sleep(0),
            cascade_mode=None,
            _cascade_mode=None,
        )

        async def fake_get_device() -> types.SimpleNamespace:
            return device

        bridge.get_device = fake_get_device
        bridge.publish_state = lambda: asyncio.sleep(0)

        await bridge.apply_command({"cascade_mode": "up"})

        self.assertEqual(device.cascade_mode.name, "UP")
        self.assertIsNone(device._cascade_mode)


class ValidationTests(unittest.IsolatedAsyncioTestCase):
    async def test_invalid_command_values_do_not_drop_device_offline(self) -> None:
        bridge = object.__new__(midea_mqtt_bridge.MideaBridge)
        bridge.device_lock = asyncio.Lock()
        bridge.stop_event = asyncio.Event()
        bridge.device_offline_published = False
        bridge.device_retry_delay = 5
        bridge.device_retry_at = 0.0
        bridge.mqtt = types.SimpleNamespace(publish=lambda *args, **kwargs: None)

        midea_mqtt_bridge.AC.OperationalMode = enum.Enum("OperationalMode", "AUTO COOL HEAT")
        midea_mqtt_bridge.AC.FanSpeed = enum.Enum("FanSpeed", "AUTO LOW HIGH")
        midea_mqtt_bridge.AC.SwingMode = enum.Enum("SwingMode", "OFF")
        midea_mqtt_bridge.AC.CascadeMode = enum.Enum("CascadeMode", "OFF UP DOWN")
        midea_mqtt_bridge.AC.RateSelect = enum.Enum("RateSelect", "OFF")
        midea_mqtt_bridge.AC.AuxHeatMode = enum.Enum("AuxHeatMode", "OFF")
        midea_mqtt_bridge.AC.SwingAngle = enum.Enum("SwingAngle", "OFF")
        midea_mqtt_bridge.AC.BreezeMode = enum.Enum("BreezeMode", "OFF BREEZE_AWAY BREEZE_MILD BREEZELESS")

        device = types.SimpleNamespace(
            refresh=lambda: asyncio.sleep(0),
            apply=lambda: asyncio.sleep(0),
            target_temperature=21.0,
            operational_mode=midea_mqtt_bridge.AC.OperationalMode.AUTO,
        )
        get_device_calls = 0

        async def fake_get_device() -> types.SimpleNamespace:
            nonlocal get_device_calls
            get_device_calls += 1
            return device

        bridge.get_device = fake_get_device
        bridge.publish_state = lambda: asyncio.sleep(0)

        await bridge.apply_command({"desired-temp": "abc"})
        await bridge.apply_command({"mode": "bogus"})

        self.assertEqual(get_device_calls, 0)
        self.assertFalse(bridge.device_offline_published)
        self.assertEqual(bridge.device_retry_at, 0.0)

        await bridge.apply_command({"desired-temp": "23.5"})
        self.assertEqual(get_device_calls, 1)
        self.assertEqual(device.target_temperature, 23.5)


class BreezeModeCommandTests(unittest.IsolatedAsyncioTestCase):
    async def test_apply_command_sets_only_requested_breeze_flag(self) -> None:
        bridge = object.__new__(midea_mqtt_bridge.MideaBridge)
        bridge.device_lock = asyncio.Lock()
        bridge.stop_event = asyncio.Event()
        bridge.device_offline_published = False

        midea_mqtt_bridge.AC.BreezeMode = enum.Enum("BreezeMode", "OFF BREEZE_AWAY BREEZE_MILD BREEZELESS")

        device = types.SimpleNamespace(
            refresh=lambda: asyncio.sleep(0),
            apply=lambda: asyncio.sleep(0),
            breeze_away=False,
            breeze_mild=False,
            breezeless=False,
        )

        async def fake_get_device() -> types.SimpleNamespace:
            return device

        bridge.get_device = fake_get_device
        bridge.publish_state = lambda: asyncio.sleep(0)
        bridge.mqtt = types.SimpleNamespace(publish=lambda *args, **kwargs: None)

        await bridge.apply_command({"breeze_mode": "breeze_away"})

        self.assertTrue(device.breeze_away)
        self.assertFalse(device.breeze_mild)
        self.assertFalse(device.breezeless)


class LockSerializationTests(unittest.IsolatedAsyncioTestCase):
    async def test_publish_and_apply_are_serialized(self) -> None:
        bridge = object.__new__(midea_mqtt_bridge.MideaBridge)
        bridge.device_lock = asyncio.Lock()
        bridge.stop_event = asyncio.Event()
        bridge.device_offline_published = False
        bridge.mqtt = types.SimpleNamespace(publish=lambda *args, **kwargs: None)

        events: list[str] = []
        first_refresh_started = asyncio.Event()
        release_first_refresh = asyncio.Event()

        class FakeDevice:
            def __init__(self) -> None:
                self.refresh_calls = 0
                self.power_state = False

            async def refresh(self) -> None:
                self.refresh_calls += 1
                events.append(f"refresh-{self.refresh_calls}-start")
                if self.refresh_calls == 1:
                    first_refresh_started.set()
                    await release_first_refresh.wait()
                events.append(f"refresh-{self.refresh_calls}-end")

            async def apply(self) -> None:
                events.append("apply-start")
                events.append("apply-end")

        device = FakeDevice()

        async def fake_get_device() -> FakeDevice:
            return device

        bridge.get_device = fake_get_device

        publish_task = asyncio.create_task(bridge.publish_state())
        await asyncio.wait_for(first_refresh_started.wait(), timeout=1)

        apply_task = asyncio.create_task(bridge.apply_command({"power": True}))
        await asyncio.sleep(0)
        self.assertNotIn("apply-start", events)

        release_first_refresh.set()
        await asyncio.wait_for(publish_task, timeout=1)
        await asyncio.wait_for(apply_task, timeout=1)

        self.assertLess(events.index("refresh-1-end"), events.index("apply-start"))
        self.assertGreater(events.index("apply-end"), events.index("apply-start"))


class EnergyEstimateTests(unittest.IsolatedAsyncioTestCase):
    async def test_update_energy_estimate_integrates_real_time_power(self) -> None:
        bridge = object.__new__(midea_mqtt_bridge.MideaBridge)
        bridge.energy_estimate_wh = 0.0
        bridge.energy_estimate_at = None
        bridge.energy_estimate_power_w = None

        times = iter([100.0, 1900.0])
        original_monotonic = midea_mqtt_bridge.time.monotonic
        midea_mqtt_bridge.time.monotonic = lambda: next(times)
        try:
            device = types.SimpleNamespace(_real_time_power_usage={"bcd": 1000, "binary": None})

            first = midea_mqtt_bridge.MideaBridge.update_energy_estimate(bridge, device)
            second = midea_mqtt_bridge.MideaBridge.update_energy_estimate(bridge, device)
        finally:
            midea_mqtt_bridge.time.monotonic = original_monotonic

        self.assertEqual(first, {"estimated_energy_wh": 0.0, "estimated_energy_kwh": 0.0})
        self.assertEqual(second, {"estimated_energy_wh": 500.0, "estimated_energy_kwh": 0.5})


class TelemetryActivationTests(unittest.IsolatedAsyncioTestCase):
    async def test_enable_optional_telemetry_sets_property_flags(self) -> None:
        bridge = object.__new__(midea_mqtt_bridge.MideaBridge)
        device = types.SimpleNamespace(
            enable_energy_usage_requests=False,
            enable_group5_data_requests=False,
        )

        await midea_mqtt_bridge.MideaBridge.enable_optional_telemetry(bridge, device)

        self.assertTrue(device.enable_energy_usage_requests)
        self.assertTrue(device.enable_group5_data_requests)


if __name__ == "__main__":
    unittest.main()
