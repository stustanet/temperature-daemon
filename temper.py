#!/usr/bin/python
# encoding: utf-8
#
# Handles devices reporting themselves as USB VID/PID 0C45:7401 (mine also says RDing TEMPerV1.2).
#
# Copyright 2012, 2013 Philipp Adelt <info@philipp.adelt.net>
#
# This code is licensed under the GNU public license (GPL). See LICENSE.md for details.

# originally from: https://github.com/padelt/temper-python

# minor updates (calibration, bus/device access) by:
# Maximilian Engelhardt <maxi@stusta.de>
# Johannes Naab <jn@stusta.de>

import usb
import sys
import struct
import time

VIDPIDs = [(0x0c45L,0x7401L)]
REQ_INT_LEN = 8
REQ_BULK_LEN = 8
TIMEOUT = 2000

class TemperDevice():
    def __init__(self, bus, device):
        self._device = device
        self._bus = bus
        self._handle = None

    def get_id(self):
        return self._bus.dirname, self._device.filename

    def get_temperature(self, calibration=0, format='celsius'):
        try:
            if not self._handle:
                self._handle = self._device.open()
                try:
                    self._handle.detachKernelDriver(0)
                except usb.USBError:
                    pass
                try:
                    self._handle.detachKernelDriver(1)
                except usb.USBError:
                    pass
                self._handle.setConfiguration(1)
                self._handle.claimInterface(0)
                self._handle.claimInterface(1)
                self._handle.controlMsg(requestType=0x21, request=0x09, value=0x0201, index=0x00, buffer="\x01\x01", timeout=TIMEOUT) # ini_control_transfer

            self._control_transfer(self._handle, "\x01\x80\x33\x01\x00\x00\x00\x00") # uTemperatura
            self._interrupt_read(self._handle)
            self._control_transfer(self._handle, "\x01\x82\x77\x01\x00\x00\x00\x00") # uIni1
            self._interrupt_read(self._handle)
            self._control_transfer(self._handle, "\x01\x86\xff\x01\x00\x00\x00\x00") # uIni2
            self._interrupt_read(self._handle)
            self._interrupt_read(self._handle)
            self._control_transfer(self._handle, "\x01\x80\x33\x01\x00\x00\x00\x00") # uTemperatura
            data = self._interrupt_read(self._handle)
            data_s = "".join([chr(byte) for byte in data])
            temp_c = (struct.unpack('>h', data_s[2:4])[0])
            temp_c += calibration
            temp_c *= 125.0/32000.0
            if format == 'celsius':
                return temp_c
            elif format == 'fahrenheit':
                return temp_c*1.8+32.0
            elif format == 'millicelsius':
                return int(temp_c*1000)
            else:
                raise ValueError("Unknown format")
        except usb.USBError, e:
            self.close()
            if "not permitted" in str(e):
                raise Exception("Permission problem accessing USB. Maybe I need to run as root?")
            else:
                raise

    def close(self):
        if self._handle:
            try:
                self._handle.releaseInterface()
            except ValueError:
                pass
            self._handle = None

    def _control_transfer(self, handle, data):
        handle.controlMsg(requestType=0x21, request=0x09, value=0x0200, index=0x01, buffer=data, timeout=TIMEOUT)

    def _interrupt_read(self, handle):
        return handle.interruptRead(0x82, REQ_INT_LEN)


class TemperHandler():
    def __init__(self):
        busses = usb.busses()
        # key: (bus.dirname, dev.filename), value: TemperDevice
        self._devices = {}
        for bus in busses:
            for x in bus.devices:
                if (x.idVendor,x.idProduct) in VIDPIDs:
                    tdev = TemperDevice(bus, x)
                    self._devices[tdev.get_id()] = tdev


    def get_devices(self):
        return self._devices

if __name__ == '__main__':
    th = TemperHandler()
    for i, dev in th._devices.iteritems():
        try:
            print "Device %s: %0.1f°C %0.1f°F" % (i[0]+"/"+i[1], dev.get_temperature(calibration=0), dev.get_temperature(format="fahrenheit"))
        except Exception as e:
            print e
