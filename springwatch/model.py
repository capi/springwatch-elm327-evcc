from datetime import datetime, UTC
from typing import Any, Optional


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
        self._disconnected_when: Optional[datetime] = None
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
        if value:
            self._car_connected_when = datetime.now(UTC)
        else:
            self._car_disconnected_when = datetime.now(UTC)

    @property
    def car_connected_when(self):
        return self._car_connected_when

    @property
    def car_disconnected_when(self):
        return self._car_disconnected_when

    def is_car_awake(self):
        r = self.battery_12v_voltage
        return self.car_connected and r.value and r.value >= self.sleep_voltage

    def is_from_current_session(self, reading: Reading) -> bool:
        con_when = self.car_connected_when
        r_when = reading.last_read
        return con_when is not None and r_when is not None and r_when >= con_when


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
