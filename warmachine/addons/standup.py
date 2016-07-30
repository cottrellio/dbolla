import asyncio
from datetime import datetime, timedelta
import functools

from .base import WarMachinePlugin


class StandUpPlugin(WarMachinePlugin):
    """
    WarMachine stand up plugin.

    Commands:
        !standup-add <24 hr time to kick off> <SunMTWThFSat> [channel]
        !standup-remove [channel]
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.standup_schedules = {}

    async def recv_msg(self, connection, message):
        if not message['message'].startswith('!standup'):
            return

        self.log.debug('standup recv: {}'.format(message))

        cmd = message['message'].split(' ')[0]
        parts = message['message'].split(' ')[1:]

        self._loop = asyncio.get_event_loop()

        if cmd == '!standup-add':
            pretty_next_standup, next_standup_secs = \
                self.get_next_standup_secs(parts[0])

            f = self._loop.call_later(
                next_standup_secs, functools.partial(
                    self.standup_schedule_func, connection, message['channel']))

            self.standup_schedules[message['channel']] = {
                'future': f,
            }
            await connection.say('Next standup in {}'.format(
                pretty_next_standup), message['channel'])
            await connection.say(str(self.standup_schedules),
                                 message['channel'])

    def standup_schedule_func(self, connection, channel):
            asyncio.ensure_future(self.start_standup(connection, channel))

    async def start_standup(self, connection, channel):
        await connection.say('@channel Time for standup', channel)
        connection.get_users_by_channel(channel)

    @classmethod
    def get_next_standup_secs(cls, time24h):
        """
        calculate the number of seconds until the next standup time
        """
        now = datetime.now()

        # if it's friday, wait 72 hours
        if now.isoweekday() == 5:
            hours = 72
        # if it's saturday, wait 48
        elif now.isoweekday() == 6:
            hours = 48
        # if it's sunday-thur wait 24
        else:
            hours = 24

        standup_hour, standup_minute = (int(s) for s in time24h.split(':'))

        future = now + timedelta(hours=hours)
        next_standup = datetime(future.year, future.month, future.day,
                                standup_hour, standup_minute)
        standup_in = next_standup-now
        return standup_in, standup_in.seconds
