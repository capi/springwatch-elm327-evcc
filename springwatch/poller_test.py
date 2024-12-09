
from datetime import UTC, datetime
from springwatch.model import CarspecificSettings, WorldView
from springwatch.poller import poll_loop_hv_battery_soc_percent


class StaticHvReaderMock:
    def __init__(self, value: float = 0.0):
        self._value = value

    def read_hv_battery_soc(self) -> float:
        return self._value


class ListHvReaderMock:
    def __init__(self, values: list[float]):
        self._values = values
        self._idx = 0

    def read_hv_battery_soc(self) -> float:
        val = self._values[self._idx]
        self._idx += 1
        return val


def test_poll_hv_missing_value():
    world = WorldView(car_connected=True)
    assert world.battery_hv_soc_percent.value is None
    soc = poll_loop_hv_battery_soc_percent(car=CarspecificSettings(), world=world, reader=StaticHvReaderMock(17.5))
    assert soc == 17.5


def test_poll_hv_minor_change_accepted_without_retry():
    world = WorldView(car_connected=True)
    world.battery_hv_soc_percent.update(100, datetime.fromtimestamp(0, UTC))
    soc = poll_loop_hv_battery_soc_percent(car=CarspecificSettings(), world=world, reader=ListHvReaderMock([99.0]))
    assert soc == 99

