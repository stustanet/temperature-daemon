#!/usr/bin/env python3

"""
This is the tempermonitoring system v2.

it is based on the work of the old temperature monitoring system and released
under the terms as stated in the LICENSE.md file.

Changelog:

2018-08 jotweh: reimplemented using a micropython-esp32
2020-04 milo: added prometheus plugin

Open issues:

- Temperature Limits
- Integrate USB Sensors
"""

import asyncio
import configparser
import sys
import time
import importlib
from datetime import datetime
from pathlib import Path
import serial_asyncio
import serial


class Sensor:
    """
    One instance as sensor posing as measurement proxy
    """

    def __init__(self, config, owid):
        self.temperature = None
        self.last_update = 0
        self.calibration = 0
        self.valid = True

        if owid not in config:
            print(f"Invalid Config: missing section {owid}")
            return

        if 'name' not in config[owid] or 'calibration' not in config[owid]:
            print(f"Invalid Config for: {owid}")
            raise RuntimeError(f"Invalid Config for: {owid}")

        self.name = config[owid]['name']
        self.calibration = config[owid]['calibration']

    def update(self, temperature):
        """
        Store a new measurement, and remember the time it was taken
        """
        self.temperature = float(temperature)
        self.last_update = time.time()


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

        self.plugins = []
        self.sensors = {}
        self._last_store = 0

        self._reader, self._writer = (None, None)

        # Test if all necessary config fields are set, that are not part of the normal
        # startup
        configtest = [
            self.config['general']['plugins'],
            self.config['collectd']['hostname'],
            self.config['collectd']['interval'],
            self.config['mail']['from'],
            self.config['mail']['to'],
            self.config['mail']['to_urgent'],
            self.config['mail']['min_delay_between_messages'],
            self.config['serial']['timeout'],
            self.config['serial']['port'],
            self.config['serial']['baudrate'],
        ]
        del configtest

        print("connecting to", self.config['serial']['port'])
        for owid in self.config:
            # Skip all known and predefined sections
            if owid in ['DEFAULT', 'serial', 'collectd', 'mail', 'warning', 'prometheus', 'general']:
                continue
            self.sensors[owid] = Sensor(self.config, owid)
        self._run_task = loop.create_task(self.run())

    async def reconnect(self):
        """
        Connect to the ESP chip
        """
        try:
            self._reader, self._writer = await serial_asyncio.open_serial_connection(
                url=self.config['serial']['port'],
                baudrate=self.config['serial']['baudrate'],
                loop=self.loop)
        except serial.SerialException:
            print("Connection failed!")
            self.loop.stop()
            raise

        # upon startup we only see garbage. (micropython starting up),
        # also it will produce warnings if the recording is started in the middle
        # of a message, so wait until the end of a message block to start the game
        # If the baudrate is wrong during micropython startup - this will also be
        # skiped.
        while True:
            try:
                if (await self._reader.readline()).decode('ascii').strip() == "":
                    break
            except UnicodeError:
                continue

    async def run(self):
        """
        Read the protocol, update the sensors or trigger a collectd update
        """
        await self.reconnect()
        last_valid_data_received = time.time()
        line = ""
        reconnected_on_error = False
        while True:
            # Wait for the next line

            if time.time() - last_valid_data_received > 10:
                await self.call_plugin("err_no_valid_data", last_line=line)
                if not reconnected_on_error:
                    reconnected_on_error = True
                    await self.reconnect()

            try:
                line = await asyncio.wait_for(
                    self._reader.readline(),
                    timeout=int(self.config['serial']['timeout']))
                print("Received: ", line)
            except asyncio.TimeoutError:
                print("No Data")
                await self.call_plugin("err_nodata")
                continue
            except serial.SerialException as exc:
                print("Problem with the serial connection - reconnecting: ", exc)
                await self.reconnect()
                continue

            try:
                line = line.decode('ascii').strip()
            except UnicodeError:
                print("Unicode error")
                continue
            # print("recv:", line)

            if line == '':
                # Block has ended
                print("Done block, storing sensors")
                await self.store_sensors()
                print("Done")
                continue

            # Try to parse the line
            try:
                owid, temp = line.split(' ')
                temp = float(temp)
            except ValueError as exc:
                print("Invaid line received: {}\n{}".format(line, exc))
                continue

            ## we have at least a valid line
            last_valid_data_received = time.time()
            reconnected_on_error = False

            sensor = self.sensors.get(owid, None)
            if not sensor:
                # If the sensor is new - notify the operators
                print("Unknown sensor")
                await self.call_plugin("err_unknown_sensor",
                                       config=self._configname,
                                       owid=owid,
                                       temp=temp)
            elif temp > 1000 or temp < -1000:
                print("Sensor invalid")
                sensor.valid = False
                # if the sensor is giving bullshit data - notify the operators
                await self.call_plugin("err_problem_sensor",
                                       owid=owid,
                                       name=sensor.name,
                                       temp=temp)
            else:
                sensor.valid = True
                # in the unlikely event that everyting is fine: log the data
                sensor.update(temp)

    async def teardown(self):
        """ Terminate all started tasks """
        self._run_task.cancel()
        try:
            await self._run_task
        except asyncio.CancelledError:
            pass

    async def call_plugin(self, call, *args, **kwargs):
        """
        Call the given method on all plugins, proxying arguments
        """
        result = {}
        for plugin in self.plugins:
            func = getattr(plugin, call, None)
            if func:
                if asyncio.iscoroutinefunction(func):
                    result[plugin.name] = await func(*args, **kwargs)
                else:
                    result[plugin.name] = func(*args, **kwargs)

    async def store_sensors(self):
        """
        Prepare the sensors to be stored and maybe send an email
        """
        sensorstr = "measurements: "
        for owid, sensor in self.sensors.items():
            if sensor.valid:
                sensorstr += "{}: {}; ".format(sensor.name, sensor.temperature)
                if sensor.last_update <= self._last_store:
                    sensor.valid = False
                    isotime = datetime.utcfromtimestamp(sensor.last_update).isoformat()
                    await self.call_plugin("err_missed_sensor",
                                           owid=owid,
                                           name=sensor.name,
                                           last_update=isotime)
            else:
                sensorstr += "{}: INVALID; ".format(sensor.name)

        print(sensorstr)
        await self.call_plugin("sensor_update")
        self._last_store = time.time()


def setup_plugin(filename, plugin):
    """
    Setup and fix plugins
    """
    if not getattr(plugin, "name", None):
        plugin.name = filename


def main():
    """
    Start the tempmonitor
    """
    loop = asyncio.get_event_loop()

    configfile = "/etc/tempermonitor.ini"
    if len(sys.argv) == 2:
        configfile = sys.argv[1]

    print("Configuring temperature monitoring system from {}.".format(configfile))
    monitor = TempMonitor(loop, configfile)

    plugin_path = Path(__file__).resolve().parent / "plugins"
    print("Loading plugins from {}".format(plugin_path))
    active_plugins = monitor.config["general"]["plugins"].split(",")
    print(f"Active plugins: {active_plugins}")

    for filename in plugin_path.glob("*.py"):
        if (plugin_path / filename).exists() and filename.stem in active_plugins:
            print("loading {}".format(filename.name))
            modname = "plugins." + filename.name.split('.')[0]
            module = importlib.import_module(modname)
            plugin = module.init(monitor)
            setup_plugin(filename, plugin)
            monitor.plugins.append(plugin)
            print("Loaded: {}".format(plugin.name))

    try:
        loop.run_forever()
    except KeyboardInterrupt:
        pass
    finally:
        loop.run_until_complete(monitor.teardown())

