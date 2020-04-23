from abc import ABCMeta

PLUGINS = dict()


class PluginMeta(ABCMeta):
    """
    Metaclass for available container backends.
    """
    def __init__(cls, name, bases, classdict):
        super().__init__(name, bases, classdict)
        PLUGINS[cls.plugin_name()] = cls


class Plugin(metaclass=PluginMeta):

    @classmethod
    def plugin_name(cls):
        return cls.__name__.lower()

    @property
    def name(self):
        return self.__class__.__name__.lower()


# import all plugins so metaclass can populare PLUGINS dict
from . import collectd, mail, prometheus, warnings
