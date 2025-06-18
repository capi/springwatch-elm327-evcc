# Dacia Spring EVCC MQTT OBD-II ELM327 Monitor

This project is a Python-based tool for monitoring and interacting with a Dacia Spring electric vehicle via an ELM327 OBD-II adapter. It connects to the car's OBD-II port (using an ELM327-compatible device over TCP), reads battery and charging information, and can publish this data to an MQTT broker or print it to the console. It also integrates with [evcc](https://github.com/evcc-io/evcc) to monitor and control charging sessions.

## Background & Motivation
There is no official API for the Dacia Spring’s charging state - only Renault’s "My Dacia" mobile app. Reverse-engineered libraries often face strict rate limits and break when APIs change. This project bypasses those issues by using a wireless OBD-II adapter to read charging and battery data directly from the vehicle.

The main goal is to optimize PV charging with evcc. Since the Dacia Spring doesn’t automatically resume charging after long pauses, polling the OBD-II port wakes the high-voltage (HV) battery system to allow charging. To reduce HV system wear, polling is limited to when the charger is connected, during charging, or if charging fails to resume; otherwise, it runs only every few hours to monitor battery status and detect drain.

## Features
- Reads 12V battery voltage, high-voltage battery State of Charge (SoC), and State of Health (SoH).
- Publishes readings to MQTT for integration with home automation or monitoring systems.
- Optionally connects to an [evcc](https://github.com/evcc-io/evcc) instance to synchronize charging state.
- Designed for use with Dacia Spring (Renault K-ZE platform) but may be adaptable to similar vehicles.

## What You Can Do With It
- Monitor your Dacia Spring's battery status remotely.
- Integrate car battery and charging data into your smart home or energy management system via MQTT.
- Automate or optimize charging using [evcc](https://github.com/evcc-io/evcc) integration.

## Adapter Compatibility
While in theory any network-enabled OBD-II adapter that supports the ELM327 protocol should work, this project has been developed and is in active use with a [`MeatPi WiCAN`](https://www.meatpi.com/products/wican) adapter. This project is not affiliated with MeatPi, but I know that it works and the firmware is open-source, which is cool.


## Getting Started

### Prerequisites
- Python 3.9+ (developed and tested under Python 3.12)
- ELM327 OBD-II adapter (WiFi/TCP recommended)
- Dacia Spring (or compatible Renault K-ZE platform vehicle)

### Installation
1. Clone this repository:
   ```sh
   git clone https://github.com/capi/springwatch-elm327-evcc.git
   cd <repo-name>
   ```
2. Install dependencies:
   ```sh
   pip install -r requirements.txt
   ```

### Configuration
- Copy `.env.template` to `.env` and fill in your settings (MQTT broker, ELM327 host/port, etc.).
- See comments in [`.env.template`](.env.template) for details on each variable.

### Usage
Run the main script:
```sh
python wican-elm327-evcc-mqtt-dacia.py
```

### Docker

You can build and run this project using Docker.

#### Build the Docker image

```sh
docker build -t springwatch-elm327-evcc .
```

#### Run the container

Replace environment variables and volume mounts as needed for your setup (check .env.template for additional variables to set.):

```sh
docker run --rm \
  --name springwatch \
  -e MQTT_BROKER_HOST=your-mqtt-broker-host \
  -e MQTT_BROKER_PORT=your-mqtt-broker-port \
  -e ELM327_HOST=your-obd-host \
  -e ELM327_PORT=your-obd-port \
  springwatch-elm327-evcc
```

You may need to adjust device access or network settings depending on your OBD-II adapter and MQTT broker configuration.

### Docker Compose

You can also use Docker Compose for easier management. Create a `docker-compose.yml` file like this:

```yaml
services:
  springwatch:
    image: springwatch-elm327-evcc
    env_file:
      - .env
    restart: unless-stopped
```

Make sure your `.env` file contains the required environment variables (see [`.env.template`](.env.template)).

Build and start the service:
```sh
docker-compose up --build -d
```

## Python Version

This project requires **Python 3.9 or newer**. It was developed and tested under **Python 3.12**. Older versions (such as Python 3.8) are not supported due to usage of newer language features.

## Project Structure
- `wican-elm327-evcc-mqtt-dacia.py`: Main entry point.
- `springwatch/`: Core logic (ELM327 communication, MQTT, polling, etc.).
- `requirements.txt`: Python dependencies.
- `.env.template`: Example environment configuration.

## License
MIT License. See [LICENSE](LICENSE).
