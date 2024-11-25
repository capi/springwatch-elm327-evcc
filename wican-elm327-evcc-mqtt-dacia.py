#!/usr/bin/env python3
from datetime import datetime, timedelta, UTC
import logging
import os
import time
import sys
from dotenv import load_dotenv
from springwatch.elm327 import Elm327Connection, Elm327Session
from springwatch.evcc import EvccClient
from springwatch.model import ModelPublisher, StdOutModelPublisher, WorldView
from typing import Optional

from springwatch.mqtt import MqttModelPublisher


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
    OBD2_SLEEP_VOLTAGE = float(print_and_get_required_env("OBD2_SLEEP_VOLTAGE", "13.0"))
    MODEL_PUBLISHER = print_and_get_required_env("MODEL_PUBLISHER", "none")
    MQTT_BROKER_HOST = print_and_get_required_env("MQTT_BROKER_HOST", "127.0.0.1")
    MQTT_BROKER_PORT = int(print_and_get_required_env("MQTT_BROKER_PORT", "1883"))
    MQTT_BASE_TOPIC = print_and_get_required_env("MQTT_BASE_TOPIC", f"springwatch/{WICAN_IP}")
    EVCC_URL = print_and_get_required_env("EVCC_URL", "")
    EVCC_LOADPOINT_ID = int(print_and_get_required_env("EVCC_LOADPOINT_ID", "1"))
    logging.info("-" * 40)
except Exception as e:
    logging.critical(str(e))
    exit(1)

MODEL_PUBLISHER_FACTORIES = {
    "none": lambda: ModelPublisher(),
    "stdout": lambda: StdOutModelPublisher(),
    "mqtt": lambda: MqttModelPublisher(host=MQTT_BROKER_HOST, port=MQTT_BROKER_PORT, base_topic=MQTT_BASE_TOPIC)
}


# =============== LOGIC ===============


def poll_loop_lv_battery(world: WorldView, session: Elm327Session):
    # we update the 12V battery reading on every tick
    # it's our indicator if car is awake or sleeping
    v = session.read_device_battery_voltage()
    if v > 0:
        if world.battery_12v_voltage.update(v):
            logging.info("Device voltage changed: %.1fV", v)


def should_poll_hv_battery_info(world: WorldView):
    if not world.car_connected or not world.session_start_when:
        return False, "Car is not connected."
    r = world.battery_hv_soc_percent
    if r.value is None:
        return True, "No known value yet."
    if not r.last_read or r.last_read < world.session_start_when:
        # last value was read last in a previous session
        return True, "Value is from previous session."
    if world.charging_ended_when and r.last_read < world.charging_ended_when:
        return True, "No update since charge end."
    if world.charging_enabled and not world.is_charging:
        # this is the wakeup case this is all about...
        td = timedelta(minutes=1)
        reason = "Charging enabled but not charging..."
    elif world.is_charging:
        td = timedelta(minutes=5)
        reason = "Currently charging."
    elif world.is_car_awake():
        reason = "Car is awake."
        td = timedelta(hours=1)
    else:
        reason = "Periodic check."
        td = timedelta(hours=6)
    res = datetime.now(UTC) - r.last_read > td
    return res, reason


def poll_loop_hv_battery_soc_percent(world: WorldView, session: Elm327Session):
    should_poll, reason = should_poll_hv_battery_info(world)
    if should_poll:
        logging.info("Polling for HV SoC: %s", reason)
        raw_soc = session.read_hv_battery_soc()
        if raw_soc > 0:
            soc_perc = raw_soc + SOC_PERCENT_CORRECTION
            world.battery_hv_soc_percent.update(soc_perc)
            logging.info("HV Battery SoC: %.2f%% (raw: %.2f%%)", soc_perc, raw_soc)
        pass


def poll_loop(world: WorldView, elm327_con: Elm327Connection, evcc: Optional[EvccClient], publisher: ModelPublisher):
    with elm327_con.new_session() as session:
        world.car_connected = True
        if world.session_start_when:
            logging.info("Session Info: started=%s (%s ago)",
                         world.session_start_when,
                         datetime.now(UTC) - world.session_start_when)
        while True:
            logging.debug("poll_loop loop start.")
            if evcc:
                evcc.update(world)
            poll_loop_lv_battery(world, session)
            poll_loop_hv_battery_soc_percent(world, session)
            publisher.publish(world)
            logging.debug("poll_loop loop end. Sleeping 3 seconds")
            time.sleep(3)


world = WorldView(sleep_voltage=OBD2_SLEEP_VOLTAGE)
evcc = EvccClient(evcc_url=EVCC_URL, loadpoint_id=EVCC_LOADPOINT_ID) if EVCC_URL else None

if MODEL_PUBLISHER in MODEL_PUBLISHER_FACTORIES:
    publisher = MODEL_PUBLISHER_FACTORIES[MODEL_PUBLISHER]()
else:
    logging.warning("Unknown publisher: %s", MODEL_PUBLISHER)
    publisher = ModelPublisher()

while True:
    world.car_connected = False
    logging.info("Waiting for elm327 device to be reachable...")
    with Elm327Connection(WICAN_IP, WICAN_ELM327_PORT) as con:
        last_session_start_when = world.session_start_when
        while not con.connect():
            logging.debug("Not connected. session_start_when=%s", world.session_start_when)
            # re-attempt connection in 1 second
            time.sleep(1)
            if last_session_start_when != world.session_start_when and not world.session_active:
                logging.info("Session timed out.")
                last_session_start_when = world.session_start_when
        logging.info("Connection to car established.")
        try:
            poll_loop(world=world, elm327_con=con, evcc=evcc, publisher=publisher)
        except Exception as e:
            logging.warning("Error in main processing loop: %s", str(e))
        finally:
            world.car_connected = False
    logging.info("Monitoring session completed.")
    time.sleep(1)
