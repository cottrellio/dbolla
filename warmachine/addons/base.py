import asyncio
import logging


class WarMachinePlugin(object):
    def __init__(self):
        self._loop = asyncio.get_event_loop()
        self.log = logging.getLogger(self.__class__.__name__)
