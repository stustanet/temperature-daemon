import time

def init(monitor):
    """ Plugin interface method """
    return PluginWarning(monitor)

class PluginWarning:
    """
    Generate all kind of warnings whenever needed and observe the sensor
    if they see a problematic situation in the container
    """
    def __init__(self, monitor):
        self.monitor = monitor

        self.revmapping = {
            sensor.name : sensor
            for sensor in self.monitor.sensors.values()
        }

        self.warning_conf = self.monitor.config['warning']

        conftest = [
            self.warning_conf['floor_sensors'],
            self.warning_conf['ceiling_sensors'],
            self.warning_conf['floor_ceiling_diff'],
            self.warning_conf['ceiling_warning_level'],
        ]
        del conftest

    def get_sensor(self, sensorname):
        """
        Resovle the reverse mapping and get back the sensor
        """
        return self.revmapping[sensorname]

    def get_stats(self, sensorlist):
        """
        Calculate mininmum, maximum average and variance over the sensor names given
        """
        sensors = [self.get_sensor(sensor) for sensor in sensorlist]
        sensors = [sensor for sensor in sensors if sensor.valid]

        if not sensors:
            return [], 0, 0, 0, 0

        avg = sum(sensor.temperature for sensor in sensors) / len(sensors)
        var = sum((sensor.temperature - avg)**2 for sensor in sensors) / len(sensors)

        sensormin = +9999
        sensormax = -9999
        for sensor in sensors:
            if sensor.temperature < sensormin:
                sensormin = sensor.temperature
            if sensor.temperature > sensormax:
                sensormax = sensor.temperature

        return sensors, sensormin, sensormax, avg, var


    async def sensor_update(self):
        """
        First generate stats and relay them to the collectd module, then use these stats
        to decide wether it is currently critical in the container, and if so, send
        warnings
        """
        # Do nothing yet
        floor_sensors, floor_min, floor_max, floor_avg, floor_var = self.get_stats(
            self.warning_conf['floor_sensors'].split(','))

        ceil_sensors, ceil_min, ceil_max, ceil_avg, ceil_var = self.get_stats(
            self.warning_conf['ceiling_sensors'].split(','))

        now = time.time()
        if floor_sensors:
            await self.monitor.call_plugin(
                "send_stats_graph", graph="stats",
                stattype="temperature-floormin", stattime=now, statval=floor_min)
            await self.monitor.call_plugin(
                "send_stats_graph", graph="stats",
                stattype="temperature-floormax", stattime=now, statval=floor_max)
            await self.monitor.call_plugin(
                "send_stats_graph", graph="stats",
                stattype="temperature-flooravg", stattime=now, statval=floor_avg)
            await self.monitor.call_plugin(
                "send_stats_graph", graph="stats",
                stattype="temperature-floorvar", stattime=now, statval=floor_var)

        if ceil_sensors:
            await self.monitor.call_plugin(
                "send_stats_graph", graph="stats",
                stattype="temperature-ceilmin", stattime=now, statval=ceil_min)
            await self.monitor.call_plugin(
                "send_stats_graph", graph="stats",
                stattype="temperature-ceilmax", stattime=now, statval=ceil_max)
            await self.monitor.call_plugin(
                "send_stats_graph", graph="stats",
                stattype="temperature-ceilavg", stattime=now, statval=ceil_avg)
            await self.monitor.call_plugin(
                "send_stats_graph", graph="stats",
                stattype="temperature-ceilvar", stattime=now, statval=ceil_var)

        if floor_sensors and ceil_sensors:
            # Else we already have sent warning messages for broken sensors

            tempdiff = ceil_avg - floor_avg
            await self.monitor.call_plugin(
                "send_stats_graph", graph="stats",
                stattype="temperature-floor_ceil_diff", stattime=now, statval=tempdiff)

            print("floor: min {:05.2f} max {:05.2f} avg {:05.2f} var {:05.2f}".format(
                    floor_min, floor_max, floor_avg, floor_var))
            print("ceil:  min {:05.2f} max {:05.2f} avg {:05.2f} var {:05.2f}".format(
                    ceil_min, ceil_max, ceil_avg, ceil_var))

            # Here comes the warning magic
            if ceil_max > int(self.warning_conf['min_ceiling_warning']):
                if  tempdiff > int(self.warning_conf['floor_ceiling_diff']):
                    await self.monitor.call_plugin("temperature_warning",
                                                source="tempdiff",
                                                name1="floor",
                                                name2="ceiling",
                                                temp1=floor_avg,
                                                temp2=ceil_avg,
                                                tempdiff=tempdiff)

            if ceil_avg > int(self.warning_conf['ceiling_warning_level']):
                await self.monitor.call_plugin("temperature_warning",
                                            source="singlehot",
                                            name="ceiling",
                                            temp=ceil_avg)
