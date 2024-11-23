#!/usr/bin/env python3
import logging
import os
import time
import socket
import sys
from dotenv import load_dotenv
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
    logging.info("-" * 40)
except Exception as e:
    logging.critical(str(e))
    exit(1)


# =============== LOGIC ===============


class Elm327Communicator:
    def __init__(self, socket: socket.socket):
        assert socket
        self._socket = socket

    def send_cmd_get_first_line(self, cmd: bytes) -> bytes:
        response = self.send_cmd_and_read_until(cmd, b'>')
        idx = response.find(b'\r')
        first_line = b""
        if idx >= 0:
            first_line = response[0:idx]
        return first_line

    def send_cmd_get_lines(self, cmd: bytes) -> list[bytes]:
        response = self.send_cmd_and_read_until(cmd, b'>')
        res = []
        for line in response.split(b'\r'):
            if len(line) > 0 and line[0] != b'>'[0]:
                res.append(line)
        return res

    def send_cmd_and_expect(self, cmd: bytes, expected=b"OK"):
        first_line = self.send_cmd_get_first_line(cmd)
        COMM_LOG.info("response=%s, expected=%s, equal=%s", first_line, expected, first_line == expected)
        return first_line == expected, first_line

    def send_cmd_and_read_until(self, cmd: bytes, terminator=b'>') -> bytes:
        self.send_cmd(cmd)
        data = b""
        while len(data) == 0 or data[-1] != terminator[0]:
            ch = self._socket.recv(1)
            data += ch
            COMM_LOG.debug(" << %s (%s): %s", ch, ord(ch), data)
        COMM_LOG.info("RX: %s", data)
        return data

    def send_cmd(self, cmd: bytes):
        COMM_LOG.info("TX: %s", cmd)
        self._socket.send(cmd)
        self._socket.send(b"\r")


class Elm327Session:
    INIT_COMMANDS = [
        # b"ATZ",    # reset         HANDLED IN RESET
        # b"ATL0",   # disable LF    HANDLED IN RESET
        b"ATE0",     # disable echo
        b"ATM0",     # disable memory
        b"ATH1",     # enable headers
        b"ATS0",     # no spaces in responses
        b"ATAT1",    # adaptive timing algorithm 1
        b"ATSP7",    # 7 - ISO 15765-4 CAN (29 bit ID, 500Kbaud)
    ]

    def __init__(self, socket: socket.socket):
        assert socket
        self._socket = socket
        self._comm = Elm327Communicator(socket)

    def __enter__(self):
        self.initialize_or_reset()
        return self

    def __exit__(self, *args):
        self._socket = None
        pass

    def initialize_or_reset(self):
        SESSION_LOG.info("Resetting and reinitializing ELM327...")
        try:
            self._comm.send_cmd_and_read_until(b"ATZ", b">")
            # send twice, if previous session was stuck in a strange state,
            # first send might not recognize ATZ as start of command
            self._comm.send_cmd_and_read_until(b"ATZ", b">")
        except TimeoutError:
            SESSION_LOG.info("Reset timed out. Trying one more time.")
            self._comm.send_cmd_and_read_until(b"ATZ", b">")
        self._comm.send_cmd_and_read_until(b"ATL0", b">")
        for cmd in Elm327Session.INIT_COMMANDS:
            ok, first_line = self._comm.send_cmd_and_expect(cmd, b"OK")
            if not ok:
                SESSION_LOG.warning("INIT ERROR: %s not acknowledged: %s", cmd, first_line)
        SESSION_LOG.info("Initialization of adapter done.")

    def read_device_battery_voltage(self) -> float:
        v = self._comm.send_cmd_get_first_line(b"ATRV")
        if len(v) == 0:
            return 0.0
        if v[-1] == ord("V"):
            v = v[0:-1]
        return float(v)

    def read_hv_battery_soc(self) -> float:
        res = self._comm.send_cmd_get_first_line(b"015B")
        if res == b'NO DATA':
            SESSION_LOG.warning("Querying HV battery SoC: NO DATA")
            return 0.0
        if len(res) != 16:
            SESSION_LOG.warning("015B: Unsupported response length %s for %s", len(res), res)
            return 0.0
        value_byte_str = res[-2:]  # last 2 hex chars
        value_byte = int(value_byte_str, 16)
        return float(value_byte) * 100 / 255


class Elm327Connection:
    def __init__(self, host: str, port: int, timeout=3):
        self.host = host
        self.port = port
        self.timeout = timeout
        self._connected = False
        self._socket: Optional[socket.socket] = None
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def connected(self) -> bool:
        return self._connected

    def connect(self) -> bool:
        self.close()
        try:
            CON_LOG.debug(f"Connecting to {self.host}:{self.port}...")
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._socket.settimeout(self.timeout)
            self._socket.connect((self.host, self.port))
            self._connected = True
            CON_LOG.info(f"Connected to {self.host}:{self.port}")
        except socket.timeout:
            CON_LOG.debug(f"Timeout occurred. Unable to connect within {self.timeout} seconds.")
        except ConnectionRefusedError:
            CON_LOG.warning("The server is not accepting connections from this host or port.")
        except Exception as e:
            CON_LOG.warning(f"An error occurred: {str(e)}")
        return self._connected

    def close(self) -> None:
        self._connected = False
        try:
            if self._socket:
                self._socket.close()
                self._socket = None
                if self._connected:
                    CON_LOG.info(f"Disconnected from {self.host}:{self.port}")
        except Exception as e:
            CON_LOG.warning(f"Failed closing previous socket: {e}")
        finally:
            self._connected = False

    def new_session(self):
        if not self._connected or not self._socket:
            raise Exception("Not connected")
        return Elm327Session(self._socket)


def poll_loop(con: Elm327Connection):
    last_device_voltage = 0.0
    last_soc_percentage = 0.0
    with con.new_session() as session:
        last_soc_percentage = 0.0
        while True:
            logging.debug("Session loop start.")
            v = session.read_device_battery_voltage()
            if (last_device_voltage != v):
                logging.info("Device voltage changed: %.1fV", v)
                last_device_voltage = v

            if last_soc_percentage == 0.0:
                raw_soc = session.read_hv_battery_soc()
                if raw_soc > 0:
                    last_soc_percentage = raw_soc + SOC_PERCENT_CORRECTION
                    logging.info("HV Battery SoC: %.2f%% (raw: %.2f%%)", last_soc_percentage, raw_soc)

            logging.debug("Session loop end. Sleep 3s.")
            time.sleep(3)


while True:
    logging.info("Waiting for elm327 device to be reachable...")
    with Elm327Connection(WICAN_IP, WICAN_ELM327_PORT) as con:
        while not con.connect():
            logging.debug("Not connected...")
            # re-attempt connection in 1 second
            time.sleep(1)
        logging.info("Connection to car established.")
        try:
            poll_loop(con)
        except Exception as e:
            logging.warning("Error in main processing loop: %s", str(e))
    logging.info("Monitoring session completed.")
    time.sleep(1)
