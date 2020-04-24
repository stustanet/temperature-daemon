import re
import asyncio
from prometheus_client import start_http_server, Gauge

from . import Plugin

stats_name_re = re.compile(r'^temperature-(?P<group>\w+)-(?P<type>\w+)$')


class Prometheus(Plugin):
    def __init__(self, monitor):
        self.loop = asyncio.get_event_loop()
        self.config = monitor.config
        self.last_store = 0
        self.monitor = monitor

        self.sensor_metrics = Gauge(
            name=self.config["prometheus"]["sensor_metric_name"],
            documentation="Container Temperature Measurements",
            labelnames=["sensor"]
        )

        self.aggregated_metrics = Gauge(
            name=self.config["prometheus"]["aggregated_metric_name"],
            documentation="Container Temperature Aggregations",
            labelnames=["group", "type"]
        )

        start_http_server(
            addr=self.config["prometheus"].get('address', 'localhost'),
            port=int(self.config["prometheus"]["port"])
        )
        print("started prometheus http server")

    async def send_stats_graph(self, graph, stattype, stattime, statval):
        """
        to be called as a plugin callback to export aggregated measurements
        """
        m = stats_name_re.match(stattype)
        if not m:
            return

        self.aggregated_metrics.labels(group=m.group('group'), type=m.group('type')).set(statval)

    async def sensor_update(self):
        """
        Receive sensor data to store them regularely into collectd
        """
        for sensor in self.monitor.sensors.values():
            if sensor.valid:
                self.sensor_metrics.labels(sensor=sensor.name).set(sensor.temperature)
