import asyncio
import logging


class WarMachinePlugin(object):
    def __init__(self, *args, **kwargs):
        self._loop = asyncio.get_event_loop()
        self.log = logging.getLogger(self.__class__.__name__)
        self.config_dir = kwargs.pop('config_dir', None)

    def recv_msg(self, *args, **kwargs):
        """
        Called when a connection receives a message. Arguments are
        ``connection`` and ``message``.

        ``connection`` is a :class:`warmachine.connections.base.Connection`
            object used to interact with the connection to a chat server.
        ``message`` is a dictionary that contains information about a message
            that was received on the connection. See
            :class:`warmachine.connections.base.Connection.read` for more
            information.
        """
        raise NotImplementedError('{} must implement `recv_msg` method'.format(
            self.__class__.__name__))
