This is the StuStaNet Temperature Monitoring System.

# Hardware Setup and Protocol

The temperature sensors are ds18x20 sensors connected via the onewire protocol
to an esp32. The esp is connected via usb-serial to the host computer.
This sends roughly every second a measurement value from one of the sensors.
After a complete round it sends an empty line.

# Dependencies

pyserial-asyncio. And >=python3.5.

# Architecture
The communications is done within the temperature_daemon.py file as well as
error handling for the sensor measurements.
It will then call functions in plugins to do the majority of the work.

The plugins are located in the `plugins` folder.

A plugin has to include a `def init(temperaturemonitor):` initializer which
returns the plugin-class. See `plugins/warnings.py` for reference.

To see which plugin functions are called with what arguments search for
`call_plugin` in the whole tree.

A plugin function can either be either async or not, both versions will be
executed properly.

Plugins can also call other plugins.

# Configuration
The system is configured via the `tempermon.ini` file, but the path can be changed
by supplying a single argument to the main executable.

It includes a bunch of default sections:

* **serial**: settings for the serial connection
* **\<pluginname>**: plugin specific settings
* **\<one-wire-id>**: every other section is interpreted as a sensor configuration
  section. The configured sensor name is used for the collectd graphs, so if a
  sensor is replaced, also change its name.
  If a sensor is missing from this list, it will generate warning mails, as well
  as for extra sensors. Only leave the sensors commented in, that are actually
  used.

# Testing
In `/tests` the testing architecture is set up.
`run_tests.sh` creates a testing socket as well as a emulated collectd socket.
Now testing can be started using the default configfile.

# Existing Plugins
If you create another plugin please add it to this list.

## Collectd
Store values into collectd when new sensor values are available as well as expose
a generic graph-storing for other plugins

## Mail
Contains the emailing system as well as all email templates.
Reacts to most `err_*` and `warn_` plugin calls and sends emails for them to the
configured clients

## Warnings
Analyse all available sensors, create statistics and analsye them and create
warnings, if required.
Here we can adopt new warning strategies.
