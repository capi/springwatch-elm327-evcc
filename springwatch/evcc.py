import logging
import requests
from springwatch.model import WorldView

EVCC_LOGGER = logging.getLogger("springwatch.evcc")


class EvccClient():
    def __init__(self, evcc_url: str, loadpoint_id: int):
        assert evcc_url, loadpoint_id is not None
        self.evcc_url = evcc_url
        self.loadpoint_id = loadpoint_id

    def load_state(self):
        url = f'{self.evcc_url}/api/state'
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        return data["result"]

    def update(self, world: WorldView):
        try:
            state = self.load_state()
            loadpoint = state["loadpoints"][self.loadpoint_id - 1]
            enabled = bool(loadpoint["enabled"])
            charging = bool(loadpoint["charging"])

            if world.charging_enabled != enabled:
                world.charging_enabled = enabled
                EVCC_LOGGER.info("evcc: Charging enabled changing from %s to %s", world.charging_enabled, enabled)
            if world.is_charging != charging:
                EVCC_LOGGER.info("evcc: Charging changing from %s to %s", world.is_charging, charging)
                world.is_charging = charging
        except Exception as e:
            EVCC_LOGGER.warning("Failed loading evcc information, defaulting to disabled: %s", e)
            world.charging_enabled = False
            world.is_charging = False
