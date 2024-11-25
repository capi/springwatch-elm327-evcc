from datetime import datetime, UTC, timedelta
from typing import Any, Optional

SESSION_TIMEOUT_GRACE_MINUTES = 2


class Reading:
    def __init__(self, name: str, short_name: str, value: Any = None, last_read: Optional[datetime] = None):
        self.name = name
        self.short_name = short_name
        self.value = value
        self.last_read: Optional[datetime] = None

    def update(self, value: Any) -> bool:
        changed = self.value != value
        self.value = value
        self.last_read = datetime.now(UTC)
        return changed


class WorldView:
    def __init__(self, sleep_voltage: float):
        self._car_connected = False
        self._car_connected_when: Optional[datetime] = None
        self._car_disconnected_when: Optional[datetime] = None
        self._session_start_when: Optional[datetime] = None  # a session may span a few short disconnects
        self.charging_enabled = False
        self.is_charging = False
        self.sleep_voltage = sleep_voltage
        self.battery_12v_voltage = Reading(name="12V Battery Voltage", short_name="12v_voltage")
        self.battery_hv_soc_percent = Reading(name="HV Battery SoC %", short_name="hv_soc")

    @property
    def car_connected(self):
        return self._car_connected

    @car_connected.setter
    def car_connected(self, value: bool):
        if value == self._car_connected:
            return
        self._car_connected = value
        now = datetime.now(UTC)
        if value:
            self._car_connected_when = now
            if self._car_disconnected_when and self._session_start_when:
                td = now - self._car_disconnected_when
                if td > timedelta(minutes=SESSION_TIMEOUT_GRACE_MINUTES):
                    self._session_start_when = None
            if self._session_start_when is None:
                self._session_start_when = now
        else:
            self._car_disconnected_when = now

    @property
    def car_connected_when(self):
        return self._car_connected_when

    @property
    def car_disconnected_when(self):
        return self._car_disconnected_when

    @property
    def session_start_when(self):
        if self._session_start_when:
            if self.car_connected:
                return self._session_start_when
            elif self._car_disconnected_when:
                now = datetime.now(UTC)
                td = now - self._car_disconnected_when
                if td < timedelta(minutes=SESSION_TIMEOUT_GRACE_MINUTES):
                    return self._session_start_when
        return None

    @property
    def session_active(self):
        return self.session_start_when is not None

    def is_car_awake(self):
        r = self.battery_12v_voltage
        return self.car_connected and r.value and r.value >= self.sleep_voltage

    def is_from_current_session(self, reading: Reading) -> bool:
        s_when = self.session_start_when
        r_when = reading.last_read
        return s_when is not None and r_when is not None and r_when >= s_when


class ModelPublisher():
    def __init__(self):
        pass

    def publish(self, world: WorldView) -> None:
        pass


class StdOutModelPublisher(ModelPublisher):
    def __init__(self):
        ModelPublisher.__init__(self)

    def publish(self, world: WorldView) -> None:
        readings = [world.battery_12v_voltage, world.battery_hv_soc_percent]
        print("-" * 50)
        for reading in readings:
            if reading.value is not None:
                assert reading.last_read
                print("%-20s: %-6s (%s)" % (reading.name, reading.value, reading.last_read))
        print("-" * 50)
