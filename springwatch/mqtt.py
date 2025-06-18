from datetime import datetime, UTC
import logging
import paho.mqtt.publish as publish
import json
from springwatch.model import ModelPublisher, WorldView
from enum import Enum

MQTT_LOGGER = logging.getLogger("springwatch.mqtt")


class MqttFormat(Enum):
    PLAIN = "PLAIN"
    JSON_WITH_TIMESTAMP = "JSON_WITH_TIMESTAMP"


class MqttModelPublisher(ModelPublisher):
    def __init__(self, host: str, port: int, base_topic: str, mqtt_format: str = "PLAIN"):
        assert host and port and base_topic
        self.host = host
        self.port = port
        self.base_topic = base_topic
        self.publish_highwater_mark = datetime.fromtimestamp(0, tz=UTC)
        # Default to PLAIN if not set or invalid
        if mqtt_format is None or mqtt_format.upper() not in MqttFormat.__members__:
            self.mqtt_format = MqttFormat.PLAIN
        else:
            self.mqtt_format = MqttFormat[mqtt_format.upper()]

    def publish(self, world: WorldView) -> None:
        MQTT_LOGGER.debug(
            "Publishing to MQTT (host=%s, port=%s, base_topic=%s, format=%s)",
            self.host, self.port, self.base_topic, self.mqtt_format
        )
        try:
            readings = [world.battery_12v_voltage, world.battery_hv_soc_percent, world.battery_hv_soh_percent]
            msgs = []
            hwm = self.publish_highwater_mark
            for reading in readings:
                if reading.value is not None and world.is_from_current_session(reading):
                    assert reading.last_read
                    if reading.last_read > self.publish_highwater_mark:
                        topic = f"{self.base_topic}/{reading.short_name}"
                        if self.mqtt_format == MqttFormat.PLAIN:
                            payload = str(reading.value)
                        else:
                            payload = json.dumps({"value": reading.value, "when": reading.last_read.isoformat()})
                        msg = {'topic': topic, 'payload': payload, 'retain': True}
                        msgs.append(msg)
                        if reading.last_read > hwm:
                            hwm = reading.last_read
            if len(msgs) > 0:
                publish.multiple(msgs, hostname=self.host, port=self.port)
                MQTT_LOGGER.debug("Published %s messages.", len(msgs))
                self.publish_highwater_mark = hwm
        except Exception as e:
            MQTT_LOGGER.warning("Failed publishing MQTT messages: %s", str(e))
