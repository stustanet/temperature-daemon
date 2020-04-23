import asyncio

from prometheus_client import start_http_server, Gauge


def init(monitor):
    return PluginPrometheus(monitor)


class PluginPrometheus:
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

    async def update_sensor_values(self, sensor):
        """
        update
        """
        self.sensor_metrics.labels(sensor=sensor.name).set(sensor.temperature)

    async def send_stats_graph(self, graph, stattype, stattime, statval):
        """
        to be called as a plugin callback to export aggregated measurements
        """
        label_group = stattype.split("-")[1]
        label_type = stattype.split("-")[2]
        self.aggregated_metrics.labels(group=label_group, type=label_type).set(statval)

    async def sensor_update(self):
        """
        Receive sensor data to store them regularely into collectd
        """
        for sensor in self.monitor.sensors.values():
            if sensor.valid:
                await self.update_sensor_values(sensor)
