import asyncio
from datetime import datetime, timedelta
import functools
from pprint import pformat

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

        # 'DM_CHANNEL': {
        #    'user': 'UID',
        #    'for_channel': 'CHID',
        # }
        self.users_awaiting_reply = {}

    async def recv_msg(self, connection, message):
        if not message['message'].startswith('!standup'):
            if message['channel'] in self.users_awaiting_reply:
                self.log.debug("Probable reply recvd from {}: {}".format(
                    message['channel'],
                    message['message']
                ))
                data = self.users_awaiting_reply[message['channel']]
                for_channel = data['for_channel']

                try:
                    user_nick = connection.user_map[data['user']]['name']
                except KeyError:
                    user_nick = data['user']

                if 'pester_task' in data:
                    self.log.debug('Stopping pester for {}'.format(user_nick))
                    data['pester_task'].cancel()

                announce_message = '{}: {}'.format(
                    user_nick,
                    message['message']
                )

                await connection.say(
                    announce_message,
                    for_channel)

                del data
                del self.users_awaiting_reply[message['channel']]
            return

        self.log.debug('standup recv: {}'.format(message))

        cmd = message['message'].split(' ')[0]
        parts = message['message'].split(' ')[1:]

        self._loop = asyncio.get_event_loop()

        if cmd == '!standup-add':
            next_standup = self.get_next_standup_secs(parts[0])

            pretty_next_standup = next_standup - datetime.now()
            next_standup_secs = pretty_next_standup.seconds

            ### DEBUG
            # next_standup_secs = 5
            ###
            f = self._loop.call_later(
                next_standup_secs, functools.partial(
                    self.standup_schedule_func, connection, message['channel']))

            self.standup_schedules[message['channel']] = {
                'future': f,
                'datetime': next_standup,
            }
            await connection.say('Next standup in {} ({})'.format(
                pretty_next_standup, next_standup), message['channel'])
            await connection.say(str(self.standup_schedules),
                                 message['channel'])

    def standup_schedule_func(self, connection, channel):
            asyncio.ensure_future(self.start_standup(connection, channel))

    def pester_schedule_func(self, connection, user_id, channel, pester):
        asyncio.ensure_future(self.standup_priv_msg(
            connection, user_id, channel, pester))

    async def start_standup(self, connection, channel):
        await connection.say('@channel Time for standup', channel)
        users = connection.get_users_by_channel(channel)

        for u in users:
            if u == connection.my_id:
                continue

            await self.standup_priv_msg(connection, u, channel)

    async def standup_priv_msg(self, connection, user_id, channel, pester=600):
        """
        Send a private message to ``user_id`` asking for their standup update.

        Args:
            connection (:class:`warmachine.base.Connection'): Connection object
                to use.
            user_id (str): User name or id to send the message to.
            channel (str): The channel the standup is for
            pester (int): Number of seconds to wait until asking the user again.
                Use 0 to disable
        """
        dm_id = connection.get_dm_id_by_user(user_id)

        self.log.debug('Messaging user: {} ({})'.format(
            connection.user_map[user_id], user_id))

        self.users_awaiting_reply[dm_id] = {
            'for_channel': channel,
            'user': user_id
        }

        self.log.debug('Adding to list of users waiting on a reply for: '
                       '{}'.format(pformat(self.users_awaiting_reply[dm_id])))

        await connection.say('What did you do yesterday? What will you '
                              'do today? do you have any blockers? '
                             '(standup for:{})'.format(channel), dm_id)

        if pester > 0:
            f = self._loop.call_later(
                pester, functools.partial(
                    self.pester_schedule_func, connection, user_id, channel,
                    pester))
            self.users_awaiting_reply[dm_id]['pester_task'] = f


    @classmethod
    def get_next_standup_secs(cls, time24h):
        """
        calculate the number of seconds until the next standup time

        Returns:
            datetime: Datetime object representing the next datetime the standup
            will begin
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
        return next_standup
        standup_in = next_standup-now
        return standup_in, standup_in.seconds
