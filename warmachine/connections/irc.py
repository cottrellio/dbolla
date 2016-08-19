import asyncio
import logging

from .base import Connection, INITALIZED
from ..utils.decorators import memoize


class AioIRC(Connection):
    def __init__(self, host, port):
        super().__init__()
        self._loop = asyncio.get_event_loop()
        self.log = logging.getLogger(self.__class__.__name__)

        self.status = INITALIZED

        self.transport = None
        self.protocol = None
        self.reader = None
        self.writer = None

        self.host = host
        self.port = port
        self.nick = 'warmachin49'
        self.user = 'WarMachine'

        self.server_info = {
            'host': ''
        }

    async def connect(self):
        self.log.info('Connecting to {}:{}'.format(self.host, self.port))

        self.reader, self.writer = await asyncio.open_connection(
            self.host, self.port)

        self.writer.write('NICK {} r\n'.format(self.nick).encode())
        self.writer.write('USER {} 8 * :War Machine\r\n'.format(
            self.user).encode())

        self.status = CONNECTED

        return True

    @asyncio.coroutine
    def read(self):
        if self.reader.at_eof():
            raise Exception('eof')

        if self.reader:
            message = yield from self.reader.readline()

            # if not self.server_info['host']:
            #     self.server_info['host'] = message.split(' ')[0].replace(':', '')

            # if message.startswith('PING'):
            #     yield from self.send_pong()
            #     return

            return message.decode().strip()

    async def send_pong(self):
        msg = 'PONG :{}'.format(self.server_info['host'])
        return self.writer.write(msg)

    @property
    @memoize
    def id(self):
        from hashlib import md5
