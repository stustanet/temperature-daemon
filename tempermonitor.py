#!/usr/bin/env python3

"""
This is the tempermonitoring system v2.

it is based on the work of the old temperature monitoring system and released
under the terms as stated in the LICENSE.md file.

Changelog:

2018-08 jotweh: reimplemented using a micropython-esp32

Open issues:

- Temperature Limits
- Integrate USB Sensors
"""


import asyncio
import configparser
import sys
import time
from datetime import datetime
from email.mime.text import MIMEText
from email.utils import formatdate
import smtplib
import serial_asyncio

UNKNOWN_SENSOR_SUBJECT = "WARNING: Unconfigured Sensor ID"
UNKNOWN_SENSOR_BODY = """Hello Guys,

An unknown sensor has been connected to the temperature monitoring service.
Please add the following section to the list of known sensors in {config}.

[{owid}]
name=changeme
calibration=0

The current temperature of the sensor is {temp}

Regards, Temperature
"""

SENSOR_MEASUREMENT_MISSED_SUBJECT = "WARNING: Sensor Measurement was missed"
SENSOR_MEASUREMENT_MISSED_BODY = """Hello Guys,

A sensor measurement was missed from the temperature monitoring.
This indicates either a problem with the hardware (check the wireing!) or the config.

ID: {owid}
NAME: {name}.

Please go check it!

Regards, Temperature
"""

SENSOR_PROBLEM_SUBJECT = "WARNING: Sensor error"
SENSOR_PROBLEM_BODY = """Hello Guys,

A sensor measurement was invalid. This might mean, that the sensor was disconnected.
Please go and check the sensor with the id

ID: {owid}
NAME: {name}.
LAST: {tem}

Regards, Temperature
"""

NO_DATA_SUBJECT = "WARNING: Did not receive any data"
NO_DATA_BODY = """Helly guys,

It has been {time} seconds since i have last received a temperature value.
This is unlikely - please come and check

Regards, Temperature
"""

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
            else:
                print("Invalid Config: missing section {}".format(owid))
        except KeyError as exc:
            print("Invalid Config: for {}: {}".format(owid, exc))
            raise

    def update(self, temperature):
        """
        Store a new measurement, and remember the time it was taken
        """
        self.temperature = temperature
        self.last_update = time.time()

class Collectd:
    """
    Implements a super simple collectd interface for only sending temperature data
    """
    def __init__(self, loop, config):
        self.loop = loop or asyncio.get_event_loop()
        self.config = config
        self.path = self.config['collectd']['socketpath']
        self._reader, self._writer = (None, None)
        self.loop.run_until_complete(self.reconnect())

    async def reconnect(self):
        """
        optionally close and then reconnect to the unix socket
        """
        if self._reader:
            self._reader.close()
        if self._writer:
            self._writer.close()

        self._reader, self._writer = await asyncio.open_unix_connection(
            path=self.path,
            loop=self.loop)

    async def send(self, sensor):
        """
        Store the temperature to collectd for fancy graphs
        """
        data = "PUTVAL \"{}/{}\" interval={} {}:{}\n".format(
            self.config['collectd']['hostname'],
            "tail-temperature/temperature-{}".format(sensor.name),
            int(self.config['collectd']['interval']),
            int(sensor.last_update),
            sensor.temperature)
        print("Sending data:", data.strip())
        self._writer.write(data.encode('utf-8'))
        await self._writer.drain()
        line = (await self._reader.readline()).decode('utf-8').strip()
        if not line:
            print("Connection reset. reconnecting")
            await self.reconnect()
        else:
            print("recv:", line)



class TempMonitor:
    """
    Interact with the esp-one-wire interface that sends:

    one-wire-id1 temperature
    one-wire-id1 temperature
    one-wire-id1 temperature

    followed by an empty line as data packet
    """

    def __init__(self, loop, configfile):
        loop = loop or asyncio.get_event_loop()

        self._configname = configfile
        self.config = configparser.ConfigParser()
        self.config.read(configfile)

        self._collectd = Collectd(loop, self.config)
        print("connecting to", self.config['serial']['port'])
        self._reader, self._writer = loop.run_until_complete(
            serial_asyncio.open_serial_connection(
                url=self.config['serial']['port'],
                baudrate=self.config['serial']['baudrate'],
                loop=loop
            ))

        self._known_sensors = {}
        self._last_store = 0

        self._mail_rate_limit = {}

        # Test if all necessary config fields are set, that are not part of the normal
        # startup
        configtest = [
            self.config['collectd']['hostname'],
            self.config['collectd']['interval'],
            self.config['mail']['from'],
            self.config['mail']['to'],
            self.config['mail']['to_urgent'],
            self.config['mail']['min_delay_between_messages'],
            self.config['serial']['timeout'],
        ]
        del configtest

        for owid in self.config:
            # Skip all known and predefined sections
            if owid in ['DEFAULT', 'serial', 'collectd', 'mail']:
                continue
            self._known_sensors[owid] = Sensor(self.config, owid)

        self._run_task = loop.create_task(self.run())

    async def run(self):
        """
        Read the protocol, update the sensors or trigger a collectd update
        """
        # upon startup we only see garbage. (micropython starting up),
        # also it will produce warnings if the recording is started in the middle
        # of a message, so wait until the end of a message block to start the game
        # If the baudrate is wrong during micropython startup - this will also be
        # skiped.
        while True:
            try:
                if await self._reader.readline().decode('ascii').strip() == "":
                    break
            except UnicodeError:
                continue

        while True:
            # Wait for the next line
            try:
                line = await asyncio.wait_for(
                    self._reader.readline(),
                    timeout=self.config['serial']['timeout'])
            except asyncio.TimeoutError:
                await self.send_mail(NO_DATA_SUBJECT, NO_DATA_BODY)
                continue

            try:
                line = line.decode('ascii')
            except UnicodeError:
                continue
            print("recv:", line)

            if line == '':
                # Block has ended
                await self.store_sensors()
                continue
            # Try to parse the line
            try:
                owid, temp = line.split(' ')
            except ValueError as exc:
                print("Invaid line received: {}\n{}".format(line, exc))
                continue

            sensor = self._known_sensors.get(owid, None)
            if not sensor:
                # If the sensor is new - notify the operators
                await self.send_mail(
                    UNKNOWN_SENSOR_SUBJECT,
                    UNKNOWN_SENSOR_BODY.format(
                        configname=self._configname,
                        owid=owid,
                        temp=temp))

            elif temp > 1000 or temp < -1000:
                # if the sensor is giving bullshit data - notify the operators
                await self.send_mail(
                    SENSOR_PROBLEM_SUBJECT,
                    SENSOR_PROBLEM_BODY.format(
                        owid=owid,
                        name=sensor.name,
                        temp=temp))
            else:
                # in the unlikely event that everyting is fine: log the data
                sensor.update(temp)

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
            if sensor.last_update <= self._last_store:
                isotime = datetime.utcfromtimestamp(sensor.last_update).isoformat()
                await self.send_mail(
                    SENSOR_MEASUREMENT_MISSED_SUBJECT,
                    SENSOR_MEASUREMENT_MISSED_BODY.format(
                        owid=owid,
                        name=sensor.name,
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

        print("Problem {}\n\n{}\n".format(subject, body))

        # Ratelimit the emails
        time_since_last_mail = time.time() - self._mail_rate_limit.get(subject, 0)
        if time_since_last_mail < self.config['mail']['min_delay_between_messages']:
            return

        self._mail_rate_limit[subject] = time.time()
        smtp = smtplib.SMTP("mail.stusta.mhn.de")
        smtp.sendmail(msg['From'], msg['To'], msg.as_string())
        smtp.quit()

def main():
    """
    Start the tempmonitor
    """
    loop = asyncio.get_event_loop()

    configfile = "/etc/temperature/tempermon.ini"
    if len(sys.argv) == 2:
        configfile = sys.argv[1]

    print("Configuring temperature monitoring system from {}.".format(configfile))
    monitor = TempMonitor(loop, configfile)
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        pass
    finally:
        loop.run_until_complete(monitor.teardown())

if __name__ == "__main__":
    main()
