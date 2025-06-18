#!/usr/bin/env python3
import logging
import os
import sys
from dotenv import load_dotenv
from springwatch.evcc import EvccClient
from springwatch.model import CarspecificSettings, ModelPublisher, StdOutModelPublisher, WorldView
from typing import Optional

from springwatch.mqtt import MqttModelPublisher
from springwatch.poller import main_loop


# =============== SETUP LOGGING ===============

FORMAT = '%(asctime)s %(name)-20s %(levelname)-8s %(message)s'
logging.basicConfig(format=FORMAT, level=logging.INFO, stream=sys.stdout)

COMM_LOG = logging.getLogger("elm327.comm")
COMM_LOG.setLevel(logging.WARNING)

SESSION_LOG = logging.getLogger("elm327.session")
SESSION_LOG.setLevel(logging.INFO)

CON_LOG = logging.getLogger("elm327.con")
CON_LOG.setLevel(logging.INFO)

# ===============  LOAD ENVIRONMENT ===============

load_dotenv()


def print_and_get_required_env(env: str, default: Optional[str] = None) -> str:
    val = os.getenv(env, default=default)
    if val is None:
        raise Exception(f"Missing required environment variable {env}")
    logging.info("%-25s = %s", env, val)
    return val


try:
    logging.info("-" * 40)
    WICAN_IP = print_and_get_required_env("ELM327_HOST", default="127.0.0.1")
    WICAN_ELM327_PORT = int(print_and_get_required_env("ELM327_PORT", default="3333"))
    SOC_PERCENT_CORRECTION = float(print_and_get_required_env("SOC_PERCENT_CORRECTION", "0.0"))
    SOC_ALMOST_FULL_LIMIT = float(print_and_get_required_env("SOC_ALMOST_FULL_LIMIT", "99.0"))
    OBD2_SLEEP_VOLTAGE = float(print_and_get_required_env("OBD2_SLEEP_VOLTAGE", "13.0"))
    MODEL_PUBLISHER = print_and_get_required_env("MODEL_PUBLISHER", "none")
    MQTT_BROKER_HOST = print_and_get_required_env("MQTT_BROKER_HOST", "127.0.0.1")
    MQTT_BROKER_PORT = int(print_and_get_required_env("MQTT_BROKER_PORT", "1883"))
    MQTT_BASE_TOPIC = print_and_get_required_env("MQTT_BASE_TOPIC", f"springwatch/{WICAN_IP}")
    MQTT_FORMAT = print_and_get_required_env("MQTT_FORMAT", "PLAIN")
    EVCC_URL = print_and_get_required_env("EVCC_URL", "")
    EVCC_LOADPOINT_ID = int(print_and_get_required_env("EVCC_LOADPOINT_ID", "1"))
    logging.info("-" * 40)
except Exception as e:
    logging.critical(str(e))
    exit(1)

MODEL_PUBLISHER_FACTORIES = {
    "none": lambda: ModelPublisher(),
    "stdout": lambda: StdOutModelPublisher(),
    "mqtt": lambda: MqttModelPublisher(
        host=MQTT_BROKER_HOST,
        port=MQTT_BROKER_PORT,
        base_topic=MQTT_BASE_TOPIC,
        mqtt_format=MQTT_FORMAT
    )
}


# =============== LOGIC ===============

world = WorldView(sleep_voltage=OBD2_SLEEP_VOLTAGE)
evcc = EvccClient(evcc_url=EVCC_URL, loadpoint_id=EVCC_LOADPOINT_ID) if EVCC_URL else None

if MODEL_PUBLISHER in MODEL_PUBLISHER_FACTORIES:
    publisher = MODEL_PUBLISHER_FACTORIES[MODEL_PUBLISHER]()
else:
    logging.warning("Unknown publisher: %s", MODEL_PUBLISHER)
    publisher = ModelPublisher()

car = CarspecificSettings(soc_percent_correction=SOC_PERCENT_CORRECTION, soc_almost_full_limit=SOC_ALMOST_FULL_LIMIT)

main_loop(car=car, world=world, evcc=evcc, publisher=publisher, elm327_host=WICAN_IP, elm327_port=WICAN_ELM327_PORT)
