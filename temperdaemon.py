#!/usr/bin/env python2.7
# encoding: utf-8

import os
import sys

os.environ["USB_DEVFS_PATH"] = "/dev/bus/usb/temper"

import socket
import temper
import threading
import time
import Queue
import smtplib
from email.mime.text import MIMEText
from email.Utils import formatdate

READINGINTERVAL = 10
EXPORTINTERVAL = 10

UNIX_SOCKET = "/var/run/collectd-unixsock"

HOSTNAME = "hugin.stusta.mhn.de"


FLOOR_LIMIT = 25
CEILING_LIMIT = 30
MAX_OUTDOOR_DIFF = 10

MAILINTERVAL = 3600

DEBUG = False

class TempReader(threading.Thread):
    def __init__(self, mq):
        threading.Thread.__init__(self)
        self.mq = mq
        self.last_mail = 0
        self.iteration = 0

    def run(self):
        while True:
            try:
                th = temper.TemperHandler()

                # TODO naming things is hard!
                for i, temp_device in th._devices.iteritems():

                    temp_sensor = temperature_sensors.get(i)

                    if temp_sensor:
                        try:
                            temp_c = temp_device.get_temperature(calibration=temp_sensor.calibration)
                            temp_sensor.update(temp_c)
                        except:
                            pass

                self.iteration += 1

            except:
                pass

            floor = temperature_sensors_by_name['floor'].temperature
            ceiling = temperature_sensors_by_name['ceiling'].temperature
            outdoor = temperature_sensors_by_name['outdoor'].temperature

            # error case: some sensor is not working!
            if floor is None:
                floor = 9000
            if ceiling is None:
                ceiling = 9001
            if outdoor is None:
                # for the difference ...
                outdoor = 0

            if self.iteration > 1 and self.last_mail + MAILINTERVAL < time.time() and \
                    ((floor > FLOOR_LIMIT and floor - MAX_OUTDOOR_DIFF > outdoor) or \
                    (ceiling > CEILING_LIMIT and ceiling - MAX_OUTDOOR_DIFF > outdoor)):

                self.last_mail = time.time()

                if DEBUG:
                    print "write mail ..."

                body = u'''DON'T PANIC!

... aber die Temperatur im Serverraum beträgt:
Boden: {:.2f} ℃
Decke: {:.2f} ℃
Outdoor: {:.2f} ℃

Der Temperator
-- 
                          oooo$$$$$$$$$$$$oooo
                      oo$$$$$$$$$$$$$$$$$$$$$$$$o
                   oo$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$o         o$   $$ o$
   o $ oo        o$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$o       $$ $$ $$o$
oo $ $ "$      o$$$$$$$$$    $$$$$$$$$$$$$    $$$$$$$$$o       $$$o$$o$
"$$$$$$o$     o$$$$$$$$$      $$$$$$$$$$$      $$$$$$$$$$o    $$$$$$$$
  $$$$$$$    $$$$$$$$$$$      $$$$$$$$$$$      $$$$$$$$$$$$$$$$$$$$$$$
  $$$$$$$$$$$$$$$$$$$$$$$    $$$$$$$$$$$$$    $$$$$$$$$$$$$$  """$$$
   "$$$""""$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$     "$$$
    $$$   o$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$     "$$$o
   o$$"   $$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$       $$$o
   $$$    $$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$" "$$$$$$ooooo$$$$o
  o$$$oooo$$$$$  $$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$   o$$$$$$$$$$$$$$$$$
  $$$$$$$$"$$$$   $$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$     $$$$""""""""
 """"       $$$$    "$$$$$$$$$$$$$$$$$$$$$$$$$$$$"      o$$$
            "$$$o     """$$$$$$$$$$$$$$$$$$"$$"         $$$
              $$$o          "$$""$$$$$$""""           o$$$
               $$$$o                                o$$$"
                "$$$$o      o$$$$$$o"$$$$o        o$$$$
                  "$$$$$oo     ""$$$$o$$$$$o   o$$$$""
                     ""$$$$$oooo  "$$$o$$$$$$$$$"""
                        ""$$$$$$$oo $$$$$$$$$$
                                """"$$$$$$$$$$$
                                    $$$$$$$$$$$$
                                     $$$$$$$$$$"
                                      "$$$""""
'''

                msg = MIMEText(body.format(floor, ceiling, outdoor),  _charset="UTF-8")
                src = "Temperator <root@hugin.stusta.mhn.de>"
                msg['Subject'] = u"Temperaturalarm Serverraum"
                msg['From'] = src
                if DEBUG:
                    dst = ["jn@stusta.de", "maxi@stusta.de"]
                else:
                    dst = ["admins@stustanet.de"]
                msg['To'] = ", ".join(dst)
                msg['Date'] = formatdate(localtime=True)

                self.mq.put((src, dst, msg.as_string()))

            time.sleep(READINGINTERVAL)


class Mail0r(threading.Thread):
    def __init__(self, mq):
        threading.Thread.__init__(self)
        self.mq = mq

    def run(self):
        while True:
            try:
                sender, recipient, msg = self.mq.get(True, 3600)
            except Exception as e:
                if DEBUG:
                    print e
                continue

            try:
                s = smtplib.SMTP("localhost")
                s.sendmail(sender, recipient, msg)
                s.quit()
            except Exception as e:
                if DEBUG:
                    print e
                pass


class Exp0rt0r(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)

        self.socket = None

    def run(self):
        while True:
            if not self.socket:
                s = socket.socket(socket.AF_UNIX)
                try:
                    s.connect(UNIX_SOCKET)
                    self.socket = s
                except Exception as e:
                    if DEBUG:
                        print e
                    pass

            for temp_sensor in temperature_sensors.values():
                temp_c, exported = temp_sensor.get_export()

                if self.socket and not exported:
                    data = "PUTVAL \"%s/tail-temperature/temperature-%s\" interval=%i N:%f\n" % \
                            (HOSTNAME, temp_sensor.name, EXPORTINTERVAL, temp_c)
                    try:
                        if DEBUG:
                            print "write", data
                        self.socket.send(data)
                    except Exception as e:
                        if DEBUG:
                            print e
                        try:
                            self.socket.close()
                        except:
                            pass
                        self.socket = None

            time.sleep(EXPORTINTERVAL)


class TempSensor():
    def __init__(self, name, calibration, bus, device):
        self.name = name
        self.calibration = calibration
        self.bus = bus
        self.device = device

        self.last_updated = None
        self.temperature = None
        self.exported = True

        self._lock = threading.RLock()

    @property
    def usb_id(self):
        return self.bus, self.device

    def update(self, temperature):
        with self._lock:
            self.temperature = temperature
            self.exported = False
            self.last_updated = time.time()
        if DEBUG:
            print "update", self

    def get_export(self):
        with self._lock:
            exported = self.exported
            self.exported = True
            if DEBUG:
                print "read", self
            return self.temperature, exported

    def __str__(self):
        with self._lock:
            return "%s (bus:%s, device:%s, calibration:%i) temperature: %s, last_updated:%s, exported:%s" % \
                    (self.name, self.bus, self.device, self.calibration, self.temperature, self.last_updated,
                            self.exported)

temperature_sensors = {}
temperature_sensors_by_name = {}

for name, calibration, bus, device in [('floor', 500, '001', '001'), ('ceiling', 300, '002', '001'), ('outdoor', 330, '003', '001')]:
    temperature_sensors[(bus, device)] = TempSensor(name, calibration, bus, device)

    temperature_sensors_by_name[name] = temperature_sensors[(bus, device)]

if __name__ == "__main__":
    mailqueue = Queue.Queue()

    readerfred = TempReader(mailqueue)
    readerfred.setDaemon(True)
    readerfred.start()

    time.sleep(2)
    exp0rtfred = Exp0rt0r()
    exp0rtfred.setDaemon(True)
    exp0rtfred.start()

    mail0r = Mail0r(mailqueue)
    mail0r.setDaemon(True)
    mail0r.start()

    while True:
        time.sleep(3600)

