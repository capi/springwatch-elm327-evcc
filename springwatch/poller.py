from datetime import UTC, datetime, timedelta
import logging
import time
from typing import Optional
from springwatch.elm327 import Elm327Connection, Elm327Session
from springwatch.evcc import EvccClient
from springwatch.model import CarspecificSettings, ModelPublisher, WorldView


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


def poll_loop_hv_battery_soc_percent(car: CarspecificSettings, world: WorldView, session: Elm327Session):
    should_poll, reason = should_poll_hv_battery_info(world)
    if should_poll:
        logging.info("Polling for HV SoC: %s", reason)
        raw_soc = session.read_hv_battery_soc()
        if raw_soc > 0:
            soc_perc = raw_soc + car.soc_percent_correction
            world.battery_hv_soc_percent.update(soc_perc)
            logging.info("HV Battery SoC: %.2f%% (raw: %.2f%%)", soc_perc, raw_soc)
        pass


def poll_loop(car: CarspecificSettings, world: WorldView, elm327_con: Elm327Connection,
              evcc: Optional[EvccClient], publisher: ModelPublisher):
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
            poll_loop_hv_battery_soc_percent(car, world, session)
            publisher.publish(world)
            logging.debug("poll_loop loop end. Sleeping 3 seconds")
            time.sleep(3)


def main_loop(car: CarspecificSettings,
              world: WorldView,
              evcc: Optional[EvccClient],
              publisher: ModelPublisher,
              elm327_host: str, elm327_port: int):
    while True:
        world.car_connected = False
        logging.info("Waiting for elm327 device to be reachable...")
        with Elm327Connection(elm327_host, elm327_port) as con:
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
                poll_loop(car=car, world=world, elm327_con=con, evcc=evcc, publisher=publisher)
            except Exception as e:
                logging.warning("Error in main processing loop: %s", str(e))
            finally:
                world.car_connected = False
        logging.info("Monitoring session completed.")
        time.sleep(1)
