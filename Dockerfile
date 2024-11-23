FROM python:3.12-slim

RUN useradd --create-home --shell /bin/bash --uid 1000 --user-group user
RUN pip3 install pyserial paho-mqtt

COPY . /app
WORKDIR /app
RUN pip3 install -r requirements.txt

USER user

ENV ELM327_HOST="127.0.0.1"
ENV ELM327_PORT="3333"
ENV SOC_PERCENT_CORRECTION="0.0"

ENTRYPOINT [ "/usr/local/bin/python3", "wican-elm327-evcc-mqtt-dacia.py" ]
