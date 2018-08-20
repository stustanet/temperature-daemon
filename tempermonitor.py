#!/usr/bin/env python3

import asyncio
import configparser
import time
from datetime import datetime

from email.mime.text import MIMEText
from email.utils import formatdate

import smtplib

import serial_asyncio

UNKNOWN_SENSOR_HEADER = "WARNING: Unknown Sensor ID"
UNKNOWN_SENSOR_BODY = """Hello Guys,

An unknown Sensor has been connected to the Temperature monitoring service.
Please add the sensor to the list of known sensors: {config}.

The SensorID is {owid}
Its current Temperature is {temp}

Regards, Temperature"""

SENSOR_MEASUREMENT_MISSED = "WARNING: Sensor Measurement was missed"
SENSOR_MEASUREMENT_MISSED = """Hello Guys,

A Sensor measurement was missed from the temperature monitoring.

The sensor in question is {owid}, named {name}.

Please go check it!

Regards, Temperature"""


class Sensor:
    """
    One instance as sensor posing as measurementproxy
    """
    def __init__(self, config, owid):
        self.temperature = None
        self.last_update = 0
        self.calibration = 0

        try:
            if owid in config:
                self.name = config[owid]['name']
                self.calibration = config[owid]['calibration']
        except KeyError as exc:
            print("Invalid Config: ", exc)
            raise

    def update(self, temperature):
        """
        Store a new measurement, and remember the time it was taken
        """
        self.temperature = temperature
        self.last_update = time.time()

class Collectd:
    def __init__(self, loop, config):
        self.loop = loop or asyncio.get_event_loop()
        self.config = config

        self._reader, self._writer = self.loop.run_until_complete(
            asyncio.open_unix_connection(
                path=self.config['collectd']['socketpath'],
                loop=self.loop
            ))

    async def send(self, sensor):
        """
        Store the temperature to collectd for fancy graphs
        """
        data = "PUTVAL \"{}/{}\" interval={} {}:{}\n".format(
            self.config['collectd']['hostname'],
            sensor.name,
            int(self.config['collectd']['interval']),
            int(sensor.last_update),
            sensor.temperature)
        self._writer.write(data)
        await self._writer.drain()

class TempMonitor:
    """
    Interact with the esp-one-wire interface that sends:

    one-wire-id1 temperature
    one-wire-id1 temperature
    one-wire-id1 temperature

    followed by an empty line as data packet
    """

    def __init__(self, loop, configfile):
        self.loop = loop or asyncio.get_event_loop()

        self._configname = configfile
        self.config = configparser.ConfigParser()
        self.config.read(configfile)

        self._collectd = Collectd(self.loop, self.config)

        self._reader, self._writer = self.loop.run_until_complete(
            serial_asyncio.open_serial_connection(
                url=self.config['serial']['port'],
                baudrate=self.config['serial']['baudrate'],
                loop=self.loop
            ))

        self._known_sensors = {}
        self._last_store = 0

        # Test if all necessary config fields, that are not part of the normal
        # startup
        configtest = [
            self.config['mail']['from'],
            self.config['mail']['to'],
            self.config['mail']['to_urgent'],
        ]
        del configtest

        predefined_sections = ['serial', 'collectd', 'mail']
        for owid in self.config:
            if owid in predefined_sections:
                continue
            self._known_sensors[owid] = Sensor(self.config, owid)

        self._run_task = loop.create_task(self.run())

    async def run(self):
        """
        Read the protocol, update the sensors or trigger a collectd update
        """
        # This is just a hack to drop the micropython startup
        # The parameter has to be tuned
        await asyncio.sleep(0.1)
        self._reader.drain()
        firstrun = True

        while True:
            line = self._reader.readline()
            try:
                line = line.decode('ascii')
            except UnicodeError:
                continue

            if line == '':
                # Block has ended
                await self.store_sensors()
                firstrun = False
            elif firstrun:
                # We start recording after we have seen the first empty line
                # else our first package might be incomplete
                pass
            else:
                try:
                    owid, temp = line.split(' ')
                except ValueError as exc:
                    # TODO upon startup we only see garbage. (micropython starting up)
                    # maybe there is an efficient way of dropping those?
                    # like waiting for ~10 seconds in the beginning?
                    print("Invaid line received: {}\n{}".format(line, exc))
                    continue
                if owid not in self._known_sensors:
                    await self.send_mail(
                        UNKNOWN_SENSOR_HEADER,
                        UNKNOWN_SENSOR_BODY.format(
                            configparser=self._configname,
                            owid=owid,
                            temp=temp))
                else:
                    self._known_sensors[owid].update(temp)

    async def teardown(self):
        """ Terminate all started tasks """
        self._run_task.cancel()
        try:
            await self._run_task
        except asyncio.CancelledError:
            pass

    async def store_sensors(self):
        """
        Prepare the sensors to be stored and maybe send an email
        """
        for owid, sensor in self._known_sensors.items():
            if sensor.last_update < self._last_store:
                isotime = datetime.utcfromtimestamp(sensor.last_update).isoformat()
                self.send_mail(
                    SENSOR_MEASUREMENT_MISSED,
                    SENSOR_MEASUREMENT_MISSED.format(
                        owid=owid,
                        last_update=isotime))
            else:
                await self._collectd.send(sensor)

        self._last_store = time.time()

    async def send_mail(self, subject, body, urgent=False):
        """
        Send a mail to the configured recipients
        """
        msg = MIMEText(body, _charset="UTF-8")
        msg['Subject'] = subject
        msg['From'] = self.config['mail']['from']
        if urgent:
            msg['To'] = self.config['mail']['to_urgent']
        else:
            msg['To'] = self.config['mail']['to']

        msg['Date'] = formatdate(localtime=True)

        # Commented out for debugging reasons to not concern the admins
        smtp = smtplib.SMTP("mail.stusta.mhn.de")
        smtp.sendmail(msg['From'], msg['To'], msg.as_string())
        smtp.quit()

def main():
    """
    Start the tempmonitor
    """
    loop = asyncio.get_event_loop()
    monitor = TempMonitor(loop, "./tempermon.ini")
    loop.run_forever()
    loop.run_until_complete(monitor.teardown())

if __name__ == "__init__":
    main()
