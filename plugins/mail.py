import time
from email.mime.text import MIMEText
from email.utils import formatdate
import smtplib

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
LAST: {temp}

Regards, Temperature
"""

NO_DATA_SUBJECT = "WARNING: Did not receive any data"
NO_DATA_BODY = """Helly guys,

It has been {time} seconds since i have last received a temperature value.
This is unlikely - please come and check

Regards, Temperature
"""



def init(monitor):
    """
    Plugin initialization method to be called from the outside
    """
    return PluginMail(monitor)

class PluginMail:
    """
    Handle all the mail sending stuff
    """
    def __init__(self, monitor):
        self.monitor = monitor
        self.config = self.monitor.config

        self._mail_rate_limit = {}

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

        print("Notification: {}".format(subject))

        # Ratelimit the emails
        time_since_last_mail = time.time() - self._mail_rate_limit.get(subject, 0)
        if time_since_last_mail < int(self.config['mail']['min_delay_between_messages']):
            print("Not sending due to ratelimiting")
            return

        print("Body: {}".format(body))

        self._mail_rate_limit[subject] = time.time()
        smtp = smtplib.SMTP("mail.stusta.mhn.de")
        #smtp.sendmail(msg['From'], msg['To'], msg.as_string())
        smtp.quit()

    async def err_nodata(self, **kwargs):
        await self.send_mail(NO_DATA_SUBJECT, NO_DATA_BODY)

    async def err_unknown_sensor(self, **kwargs):
        await self.send_mail(
            UNKNOWN_SENSOR_SUBJECT,
            UNKNOWN_SENSOR_BODY.format(**kwargs))

    async def err_problem_sensor(self, **kwargs):
        await self.send_mail(
            SENSOR_PROBLEM_SUBJECT,
            SENSOR_PROBLEM_BODY.format(**kwargs))

    async def err_missed_sensor(self, **kwargs):
        await self.send_mail(
            SENSOR_MEASUREMENT_MISSED_SUBJECT,
            SENSOR_MEASUREMENT_MISSED_BODY.format(**kwargs))


    async def temperature_warning(self, source, **kwargs):
        subject = "Temperaturwarnung Serverraum"

        body = """Hi Guys,

Die Temperaturen im Serverraum werden langsam Bedenklich:

{temperatures}

Auslöser: {reason}

Aktuelle Temperaturen:
{alltemperatures}

Bitte haltet die Temperaturen im Auge und fahrt eventuell heiß laufende Server herunter

with love,
Temperator"""

        if source == "tempdiff":
            temperatures = "{name1}:{temp1}\n{name2}:{temp2}".format(**kwargs)
            reason = "Differenztemperatur: {tempdiff}".format(**kwargs)
        elif source == "singlehot":
            temperatures = "{name}:{temp}".format(**kwargs)
            reason = "Einzeltemperatur zu hoch"

        alltemperatures = '\n'.join([
            "{}: {}".format(sensor.name, sensor.temperature) if sensor.valid
            else "{}: INVALID".format(sensor.name)
            for sensor in self.monitor.sensors.values() ])

        await self.send_mail(subject, body.format(
            temperatures=temperatures, reason=reason, alltemperatures=alltemperatures))
