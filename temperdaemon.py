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
import ow
import logging
from collections import deque, namedtuple
from email.mime.text import MIMEText
from email.Utils import formatdate

logging.basicConfig(format='%(asctime)s:%(name)s:%(levelname)s:%(message)s', level=logging.DEBUG)
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

READINGINTERVAL = 10

UNIX_SOCKET = "/var/run/collectd-unixsock"

HOSTNAME = "hugin.stusta.mhn.de"


FLOOR_LIMIT = 25
CEILING_LIMIT = 30
MAX_OUTDOOR_DIFF = 10

MAILINTERVAL = 3600

SPAM = False
#SPAM = True

class TempReader(threading.Thread):
    def __init__(self, export_queue, mail_queue):
        threading.Thread.__init__(self)
        self.export_queue = export_queue
        self.mail_queue = mail_queue
        self.last_mail = 0
        self.iteration = 0

    def queue_mail(self, floor, ceiling, outdoor):
        logger.debug("write mail ...")

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
        if SPAM:
            dst = ["jn@stusta.de", "maxi@stusta.de", "markus.hefele@stusta.net"]
        else:
            dst = ["admins@stustanet.de"]
        msg['To'] = ", ".join(dst)
        msg['Date'] = formatdate(localtime=True)

        self.mail_queue.put((src, dst, msg.as_string()))

    def run(self):
        while True:
            logger.debug("reading loop")
            start = time.time()
            try:
                th = temper.TemperHandler()

                # TODO naming things is hard!
                for i, temp_device in th._devices.iteritems():

                    temp_sensor = temperature_sensors.get(i)

                    if temp_sensor:
                        try:
                            temp_c = temp_device.get_temperature(calibration=temp_sensor.calibration)
                            record = temp_sensor.update(temp_c)
                            self.export_queue.put(record)
                        except Exception as e:
                            logger.debug(e)
                            #logger.exception(e)

            except Exception as e:
                logger.exception(e)

            try:
                ow.init( 'localhost:4304' )
                for a, owid in iter(temperature_sensors):
                    if a == 'serial':
                        temp_sensor = temperature_sensors.get((a, owid))

                        try:
                            temp_c = float(ow.Sensor( '/uncached/'+ owid ).temperature)
                            if temp_c != float('85'):
                                record = temp_sensor.update(temp_c)
                                self.export_queue.put(record)
                        except Exception as e:
                            logger.debug(e)

                # memory leak?
                #ow.finish()

            except Exception as e:
                logger.exception(e)

            self.iteration += 1

            now = time.time()

            floor, floor_last, floor_avg = temperature_sensors_usb_by_name['floor'].get_current_and_average()
            ceiling, ceiling_last, ceiling_avg = temperature_sensors_usb_by_name['ceiling'].get_current_and_average()
            outdoor, outdoor_last, outdoor_avg = temperature_sensors_usb_by_name['outdoor'].get_current_and_average()

            falling = False

            if (floor is not None and floor_avg is not None and floor <= floor_avg and
                ceiling is not None and ceiling_avg is not None and ceiling <= ceiling_avg and
                    outdoor is not None and outdoor_avg is not None and outdoor <= outdoor_avg):

                falling = True

            # error case: some sensor is not working!
            error = False

            if floor is None or (floor_last is not None and floor_last + MAILINTERVAL < now):
                error = True
                floor = 9000
            if ceiling is None or (ceiling_last is not None and ceiling_last + MAILINTERVAL < now):
                error = True
                ceiling = 9001
            if outdoor is None or (outdoor_last is not None and outdoor_last + MAILINTERVAL < now):
                # for the difference ...
                error = True
                outdoor = 0


            if (self.iteration > 1 and self.last_mail + MAILINTERVAL < now and
                    (error or (not falling and
                    ((floor > FLOOR_LIMIT and floor - MAX_OUTDOOR_DIFF > outdoor) or
                    (ceiling > CEILING_LIMIT and ceiling - MAX_OUTDOOR_DIFF > outdoor))))):

                self.last_mail = now
                self.queue_mail(floor, ceiling, outdoor)

            sys.stdout.flush()

            wait = start + READINGINTERVAL - time.time()
            if wait > 0:
                time.sleep(wait)


class Mail0r(threading.Thread):
    def __init__(self, mail_queue):
        threading.Thread.__init__(self)
        self.mail_queue = mail_queue

    def run(self):
        while True:
            try:
                sender, recipient, msg = self.mail_queue.get(True, 3600)
            except Queue.Empty as e:
                logger.debug(e)
                continue

            try:
                s = smtplib.SMTP("localhost")
                s.sendmail(sender, recipient, msg)
                s.quit()
            except Exception as e:
                logger.debug(e)


CollectdRecord = namedtuple("CollectdRecord", ["hostname", "path", "interval", "epoch", "value"])


class Exp0rt0r(threading.Thread):
    def __init__(self, export_queue):
        threading.Thread.__init__(self)

        self.socket = None

        # CollectdRecords
        self.export_queue = export_queue

    def run(self):
        while True:
            record = None
            try:
                record = self.export_queue.get(True, 3600)
            except Queue.Empty as e:
                continue

            if not self.socket:
                s = socket.socket(socket.AF_UNIX)
                try:
                    s.connect(UNIX_SOCKET)
                    s.setblocking(False)
                    self.socket = s
                except Exception as e:
                    logger.debug(e)
                    time.sleep(1)
                    continue

            data = "PUTVAL \"%s/%s\" interval=%i %i:%s\n" % \
                    (record.hostname, record.path, int(record.interval), int(record.epoch), record.value)

            try:
                logger.debug("socket write: %s", data.strip())
                self.socket.send(data)

                recv = []
                while True:
                    try:
                        recv = self.socket.recv(1<<12)
                    except socket.error as e:
                        if e.errno == 11:  #EAGAIN
                            break
                        raise e

                recv = ''.join(recv)

                logger.debug("socket read: %s", recv.strip())

            except Exception as e:
                logger.debug(e)
                try:
                    self.socket.close()
                except:
                    pass
                self.socket = None


class TempSensor(object):
    def __init__(self, name):
        self.name = name

        self._path = "tail-temperature/temperature-%s" % (name, )
        self._interval = READINGINTERVAL

        self.last_updated = None
        self.temperature = None

        self.history = deque()

        self._lock = threading.RLock()


    def update(self, temperature):
        with self._lock:
            now = time.time()

            while self.history and self.history[0][1] < (now - MAILINTERVAL):
                self.history.popleft()

            if self.last_updated is not None and self.temperature is not None:
                self.history.append((self.temperature, self.last_updated))

            self.temperature = temperature
            self.last_updated = now

            logger.debug("update %s", self)

            return CollectdRecord(HOSTNAME, self._path, int(self._interval),
                    int(self.last_updated), "%f" % (self.temperature,))

    def get_current_and_average(self):
        with self._lock:
            avg = None
            if self.history:
                avg = float(sum(i[0] for i in self.history))/len(self.history)

            return self.temperature, self.last_updated, avg

    def __str__(self):
        with self._lock:
            return "%s temperature: %s, last_updated:%s" % \
                    (self.name, self.temperature, self.last_updated)


class TempSensorUSB(TempSensor):
    def __init__(self, name, calibration, bus, device):
        super(TempSensorUSB, self).__init__(name)

        self.calibration = calibration
        self.bus = bus
        self.device = device

    @property
    def usb_id(self):
        return self.bus, self.device

    def __str__(self):
        with self._lock:
            return "%s (bus:%s, device:%s, calibration:%i) temperature: %s, last_updated:%s" % \
                    (self.name, self.bus, self.device, self.calibration, self.temperature, self.last_updated)

class TempSensorSerial(TempSensor):
    def __init__(self, name, owid):
        super(TempSensorSerial, self).__init__(name)
        self.owid = owid

    def __str__(self):
        with self._lock:
            return "%s (owid:%s) temperature: %s, last_updated:%s" % \
                    (self.name, self.owid, self.temperature, self.last_updated)

temperature_sensors = {}
#TODO:Type in key, only one dict?
temperature_sensors_usb_by_name = {}
temperature_sensors_serial_by_name = {}

for name, calibration, bus, device in [('floor', 500, '001', '001'), ('ceiling', 300, '002', '001'), ('outdoor', 330, '003', '001')]:
    temperature_sensors[(bus, device)] = TempSensorUSB(name, calibration, bus, device)

    temperature_sensors_usb_by_name[name] = temperature_sensors[(bus, device)]

for name, owid in [('floorserial', '10.C238A5010800'), ('ceilserial', '10.0C33A5010800')]:
    temperature_sensors[('serial', owid)] = TempSensorSerial(name, owid)

    temperature_sensors_serial_by_name[name] = temperature_sensors[('serial', owid)]

if __name__ == "__main__":
    mail_queue = Queue.Queue()
    export_queue = Queue.Queue()

    readerfred = TempReader(export_queue, mail_queue)
    readerfred.setDaemon(True)
    readerfred.start()

    exp0rtfred = Exp0rt0r(export_queue)
    exp0rtfred.setDaemon(True)
    exp0rtfred.start()

    mail0r = Mail0r(mail_queue)
    mail0r.setDaemon(True)
    mail0r.start()

    while True:
        time.sleep(3600)

