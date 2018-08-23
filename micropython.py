"""
This code is designed to run on an ESP32 for grabbing temperature data from
ds18x20 sensors via the onewire protocol and sending them via serial to the
connected host. It should be trivial to port it to different platforms.

The Protocol is dead simple:

ONEWIRE-ID1 TEMPERATURE1
ONEWIRE-ID2 TEMPERATURE2
...
<Empty Line>

When a sensor has problems reading, it sends as temperature 9001.

New sensors are only detected upon powerup, so you have to reboot in order to
extend the sensor network.

The sensors have a parasitic-power-mode which is NOT TO BE USED here.
Please connect all three pins, and multiplex as you please.
"""

import machine
import time
import onewire, ds18x20
import ubinascii

class reader:

    def __init__(self):

        self.di = machine.Pin(13)

        self.ds = ds18x20.DS18X20(onewire.OneWire(self.di))

        #scan for sensors
        self.roms = self.ds.scan()

    def run(self):
        while 1:
            time.sleep_ms(240)
            self.ds.convert_temp()
            time.sleep_ms(750)
            for rom in self.roms:
                print(ubinascii.hexlify(rom).decode('utf-8'), end=' ')
                try:
                    print(self.ds.read_temp(rom))
                except:
                    print(9001)
            print()
