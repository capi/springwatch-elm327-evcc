#!/usr/bin/env python3
from datetime import datetime, timedelta, UTC
import logging
import os
import time
import sys
from dotenv import load_dotenv
from springwatch.elm327 import Elm327Connection, Elm327Session
from springwatch.model import WorldView
from typing import Optional


# =============== SETUP LOGGING ===============

FORMAT = '%(asctime)s %(name)-15s %(levelname)-7s %(message)s'
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
    logging.info("-" * 40)
except Exception as e:
    logging.critical(str(e))
    exit(1)


# =============== LOGIC ===============


def poll_loop_lv_battery(world: WorldView, session: Elm327Session):
    # we update the 12V battery reading on every tick
    # it's our indicator if car is awake or sleeping
    v = session.read_device_battery_voltage()
    if v > 0:
        if world.battery_12v_voltage.update(v):
            logging.info("Device voltage changed: %.1fV", v)


def should_poll_hv_battery_info(world: WorldView):
    if not world.car_connected or not world.car_connected_when:
        return False
    r = world.battery_hv_soc_percent
    if r.value is None:
        return True
    if not r.last_read or r.last_read < world.car_connected_when:
        # last value was read last in a previous session
        return True
    # update every 2 minutes
    td: timedelta
    if world.charging:
        td = timedelta(minutes=5)
    elif world.is_car_awake():
        td = timedelta(hours=1)
    else:
        td = timedelta(hours=6)
    return datetime.now(UTC) - r.last_read > td



def poll_loop_hv_battery_soc_percent(world: WorldView, session: Elm327Session):
    if should_poll_hv_battery_info(world):
        raw_soc = session.read_hv_battery_soc()
        if raw_soc > 0:
            soc_perc = raw_soc + SOC_PERCENT_CORRECTION
            world.battery_hv_soc_percent.update(soc_perc)
            logging.info("HV Battery SoC: %.2f%% (raw: %.2f%%)", soc_perc, raw_soc)
        pass


def poll_loop(world: WorldView, elm327_con: Elm327Connection):
    with elm327_con.new_session() as session:
        world.car_connected = True
        while True:
            logging.debug("Session loop start.")
            poll_loop_lv_battery(world, session)
            poll_loop_hv_battery_soc_percent(world, session)
            logging.debug("Session loop end. Sleeping 3 seconds")
            time.sleep(3)


world = WorldView(sleep_voltage=OBD2_SLEEP_VOLTAGE)
while True:
    world.car_connected = False
    logging.info("Waiting for elm327 device to be reachable...")
    with Elm327Connection(WICAN_IP, WICAN_ELM327_PORT) as con:
        while not con.connect():
            logging.debug("Not connected...")
            # re-attempt connection in 1 second
            time.sleep(1)
        logging.info("Connection to car established.")
        try:
            poll_loop(world=world, elm327_con=con)
        except Exception as e:
            logging.warning("Error in main processing loop: %s", str(e))
        finally:
            world.car_connected = False
    logging.info("Monitoring session completed.")
    time.sleep(1)
