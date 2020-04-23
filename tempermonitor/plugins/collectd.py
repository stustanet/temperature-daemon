import asyncio
import time

from . import Plugin


class Collectd(Plugin):
    """
    Implements a super simple collectd interface for only sending temperature data
    """

    def __init__(self, monitor):
        self.loop = asyncio.get_event_loop()
        self.config = monitor.config
        self.path = self.config['collectd']['socketpath']
        self._reader, self._writer = (None, None)
        self.loop.run_until_complete(self.reconnect())

        self.monitor = monitor

        self.last_store = 0

    async def reconnect(self):
        """
        optionally close and then reconnect to the unix socket
        """
        if self._writer:
            self._writer.close()

        self._reader, self._writer = await asyncio.open_unix_connection(
            path=self.path,
            loop=self.loop)

    async def _send(self, identifier, interval, timestamp, value):
        """
        The collectd naming convention is:
         host "/" plugin ["-" plugin instance] "/" type ["-" type instance]
         Whereby:
         - host: local host name
         - plugin: the tab in CGP
         - plugin-instance: the graph
         - type the line in the graph
         - type instance : if there are more than one "temperature"s
        """

        data = "PUTVAL \"{}/{}\" interval={} {}:{}\n".format(
            self.config['collectd']['hostname'],
            identifier,
            interval,
            timestamp,
            value)
        try:
            #print("Sending data:", data.strip())
            self._writer.write(data.encode('utf-8'))
            await self._writer.drain()
        except:
            await self.reconnect()
            return

        try:
            line = await asyncio.wait_for(self._reader.readline(), 1)
        except asyncio.TimeoutError:
            print("Collectd did not respond.")
            return
        line = line.decode('utf-8').strip()
        if not line:
            print("Connection reset. reconnecting")
            await self.reconnect()
        else:
            pass
            # print("recv:", line)

    async def send_sensor_values(self, sensor):
        """
        Store the temperature to collectd for fancy graphs
        """
        await self._send("tail-temperature/temperature-{}".format(sensor.name),
                         int(self.config['collectd']['interval']),
                         int(sensor.last_update),
                         sensor.temperature)

    ## Plugin Callbacks ##
    async def send_stats_graph(self, graph, stattype, stattime, statval):
        """
        to be called as a plugin callback to store stuff into collectd
        """
        await self._send("tail-{}/{}".format(graph, stattype),
                         int(self.config['collectd']['interval']),
                         int(stattime),
                         statval)

    async def sensor_update(self):
        """
        Receive sensor data to store them regularely into collectd
        """
        for sensor in self.monitor.sensors.values():
            if sensor.valid:
                await self.send_sensor_values(sensor)
        self.last_store = time.time()
