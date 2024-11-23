from datetime import datetime
from typing import Any, Optional


class Reading:
    def __init__(self, name: str, value: Any = None, last_read: Optional[datetime] = None):
        self.name = name
        self.value = value
        self.last_read: Optional[datetime] = None

    def update(self, value: Any) -> bool:
        changed = self.value != value
        self.value = value
        self.last_read = datetime.now()
        return changed


class WorldView:
    def __init__(self, sleep_voltage: float):
        self._car_connected = False
        self._car_connected_when: Optional[datetime] = None
        self._disconnected_when: Optional[datetime] = None
        self.charging = False
        self.sleep_voltage = sleep_voltage
        self.battery_12v_voltage = Reading(name="12V Battery Voltage")
        self.battery_hv_soc_percent = Reading(name="HV Battery SoC %")

    @property
    def car_connected(self):
        return self._car_connected

    @car_connected.setter
    def car_connected(self, value: bool):
        if value == self._car_connected:
            return
        self._car_connected = value
        if value:
            self._car_connected_when = datetime.now()
        else:
            self._car_disconnected_when = datetime.now()

    @property
    def car_connected_when(self):
        return self._car_connected_when

    @property
    def car_disconnected_when(self):
        return self._car_disconnected_when

    def is_car_awake(self):
        r = self.battery_12v_voltage
        return self.car_connected and r.value and r.value >= self.sleep_voltage
