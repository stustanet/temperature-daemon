"""
This code is designed to run on an ESP8266 for grabbing temperature data from
ds18x20 sensors via the onewire protocol and sending them via serial to the
connected host. It should be trivial to port it to different platforms.
It also grabs data from one BME280 via I2C.

The Protocol is dead simple:

ONEWIRE-ID1 TEMPERATURE1 (in degree C)
ONEWIRE-ID2 TEMPERATURE2 (in degree C)
BME280-TEMPERATURE TEMPERATUREBME (in degree C)
BME280-PRESSURE PRESSUREBME (in hPa)
BME280-HUMIDITY HUMIDITYBME (in %rH)
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
import BME280

di = machine.Pin(13)
ds = ds18x20.DS18X20(onewire.OneWire(di))

scl = machine.Pin(5)
sda = machine.Pin(4)

i2c = machine.I2C(scl=scl, sda=sda, freq=10000)
bme = BME280.BME280(i2c=i2c)

# scan for onewire sensors
roms = ds.scan()

while 1:
    time.sleep_ms(240)
    ds.convert_temp()
    time.sleep_ms(750)
    for rom in roms:
        print(ubinascii.hexlify(rom).decode('utf-8'), end=' ')
        try:
            print(ds.read_temp(rom))
        except:
            print(9001)
    print("BME280_temperature",bme.temperature)
    print("BME280_pressure", bme.pressure)
    print("BME280_humidity", bme.humidity)
    print()

