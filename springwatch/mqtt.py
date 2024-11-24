import logging
import paho.mqtt.publish as publish
import json
from springwatch.model import ModelPublisher, WorldView

MQTT_LOGGER = logging.getLogger("springwatch.mqtt")


class MqttModelPublisher(ModelPublisher):
    def __init__(self, host: str, port: int, base_topic: str):
        assert host and port and base_topic
        self.host = host
        self.port = port
        self.base_topic = base_topic

    def publish(self, world: WorldView) -> None:
        MQTT_LOGGER.debug("Publishing to MQTT (host=%s, port=%s, base_topic=%s)", self.host, self.port, self.base_topic)
        try:
            readings = [world.battery_12v_voltage, world.battery_hv_soc_percent]
            msgs = []
            for reading in readings:
                if reading.value is not None and world.is_from_current_session(reading):
                    assert reading.last_read
                    topic = f"{self.base_topic}/{reading.short_name}"
                    payload = {
                        "value": reading.value,
                        "when": reading.last_read.isoformat()
                    }
                    msg = {'topic': topic, 'payload': json.dumps(payload), 'retain': True}
                    msgs.append(msg)
            if len(msgs) > 0:
                publish.multiple(msgs, hostname=self.host, port=self.port)
                MQTT_LOGGER.debug("Published %s messages.", len(msgs))
        except Exception as e:
            MQTT_LOGGER.warning("Failed publishing MQTT messages: %s", str(e))
