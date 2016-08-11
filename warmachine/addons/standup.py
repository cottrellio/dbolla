import asyncio
from datetime import datetime, timedelta
import functools
import json
from pprint import pformat

from .base import WarMachinePlugin


class StandUpPlugin(WarMachinePlugin):
    """
    WarMachine stand up plugin.

    Commands:
        In a channel:
            !standup-add <24 hr time to kick off>
            !standup-remove
        Direct Message:
            !standup-schedules
            !standup-waiting_replies
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # 'CHANNEL': {
        #     'future': Task for running next standup,
        #     'time24': Original 24h time to schedule,
        #     'datetime': datetime object of when the next schedule will run,
        #     'ignoring': list of users to ignore when priv messaging,
        # }
        self.standup_schedules = {}

        # 'DM_CHANNEL': {
        #     'user': 'UID',
        #     'for_channel': 'CHID',
        # }
        self.users_awaiting_reply = {}

    def on_connect(self, connection):
        self.load_schedule(connection)

    async def recv_msg(self, connection, message):
        """
        When the connection receives a message this method is called. We parse
        the message for commands we want to listen for.

        Args:
            connection (Connection): the warmachine connection object
            message (dict): the warmachine formatted message
        """
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

        cmd = message['message'].split(' ')[0]
        parts = message['message'].split(' ')[1:]
        channel = message['channel']

        # ======================================================================
        # !standup-add <24h time>
        #
        # Add (or update if one exists) a schedule for standup at the given 24h
        # time M-F
        # ======================================================================
        if cmd == '!standup-add' and not channel.startswith('D'):
            # If there is already a schedule, kill the task for the old one.
            if channel in self.standup_schedules:
                self.standup_schedules[channel]['future'].cancel()
                self.log.info('Unscheduling existing schedule for {} at '
                              '{}'.format(
                                  channel,
                                  self.standup_schedules[channel]['time24h']))

            self.schedule_standup(connection, channel, parts[0])
            self.save_schedule(connection)
        # ======================================================================
        # !standup-remove
        #
        # Remove an existing schedule from the channel
        # ======================================================================
        elif cmd == '!standup-remove' and not channel.startswith('D'):
            if channel in self.standup_schedules:
                self.standup_schedules[channel]['future'].cancel()
                del self.standup_schedules[channel]
                self.save_schedule(connection)
                self.log.info('Removed standup for channel {}'.format(channel))

        # ======================================================================
        # !standup-ignore
        # !standup-ignore <comma seperated list of users to ignore>
        #
        # Ignore users provided when private messaging asking the standup
        # questions.
        # If no users are provided, display the users currently being ignored
        # ======================================================================
        elif cmd == '!standup-ignore' and not channel.startswith('D') \
             and channel in self.standup_schedules:
            if parts:
                users = ''.join(parts).split(',')
                for u in users:
                    if u not in self.standup_schedules[channel]['ignoring']:
                        self.log.info('Ignoring {} in channel {}'.format(
                            u, channel))
                        self.standup_schedules[channel]['ignoring'].append(u)
                self.save_schedule(connection)

            ignoring = ', '.join(
                self.standup_schedules[channel]['ignoring'])
            if not ignoring:
                ignoring = 'no one'

            await connection.say('Currently ignoring {}'.format(ignoring),
                                 channel)

        # ======================================================================
        # !standup-schedules
        #
        # Report the current standup schedule dict to the requesting user
        # ======================================================================
        elif channel.startswith('D') and cmd == '!standup-schedules':
            self.log.info('Reporting standup schedules to DM {}'.format(
                channel))
            await connection.say('Standup Schedules', channel)
            await connection.say('-----------------', channel)
            await connection.say(
                'Current Loop Time: {}'.format(self._loop.time()), channel)
            await connection.say(
                'Current Time: {}'.format(datetime.now()), channel)
            await connection.say(pformat(self.standup_schedules), channel)

        # ======================================================================
        # !standup-waiting_replies
        #
        # Report the data struct of users we are waiting on a reply from  to the
        # requesting user.
        # ======================================================================
        elif channel.startswith('D') and \
             cmd == '!standup-waiting_replies':
            self.log.info('Reporting who we are waiting on replies for to DM '
                          ' {}'.format(channel))
            await connection.say('Waiting for Replies From', channel)
            await connection.say('------------------------', channel)
            await connection.say(
                pformat(self.users_awaiting_reply), channel)

    def schedule_standup(self, connection, channel, time24h):
        """
        Schedules a standup by creating a Task to be run in the future.
        """
        next_standup = self.get_next_standup_secs(time24h)

        standup_td = next_standup - datetime.now()
        next_standup_secs = standup_td.seconds

        f = self._loop.call_later(
            next_standup_secs, functools.partial(
                self.standup_schedule_func, connection, channel))

        self.standup_schedules[channel] = {
            'future': f,
            'datetime': next_standup,
            'time24h': time24h,
            'ignoring': [],
        }

        self.log.info('New schedule added to channel {} for {}'.format(
            connection.channel_map[channel]['name'],
            time24h
        ))

    def standup_schedule_func(self, connection, channel):
        """
        Non-async function used to schedule the standup for a channel.

        See :meth:`start_standup`
        """
        self.log.info('Executing standup for channel {}'.format(
            connection.channel_map[channel]['name']
        ))
        asyncio.ensure_future(self.start_standup(connection, channel))

    def pester_schedule_func(self, connection, user_id, channel, pester):
        """
        Non-async function used to schedule pesters for a user.

        See :meth:`standup_priv_msg`
        """
        self.log.info('Pestering user {} to give a standup for channel '
                      '{} (interval: {}s)'.format(
                          connection.user_map[user_id]['name'],
                          connection.channel_map[channel]['name'],
                          pester))
        asyncio.ensure_future(self.standup_priv_msg(
            connection, user_id, channel, pester))

    async def start_standup(self, connection, channel):
        """
        Notify the channel that the standup is about to begin, then loop through
        all the users in the channel asking them report their standup.
        """
        await connection.say('@channel Time for standup', channel)
        users = connection.get_users_by_channel(channel)

        for u in users:
            if u == connection.my_id or \
               u in self.standup_schedules[channel]['ignoring']:
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

        Args:
            time24h (str): The 24 hour version of the time that the standup
            should run on Mon-Fri

        Returns:
            datetime: Datetime object representing the next datetime the standup
            will begin
        """
        now = datetime.now()

        standup_hour, standup_minute = (int(s) for s in time24h.split(':'))

        next_standup = datetime(now.year, now.month, now.day,
                                standup_hour, standup_minute)

        # If we've already past the time for today, schedule it for that time on the
        # next weekday
        if now > next_standup:
            # if it's friday, wait 72 hours
            if now.isoweekday() == 5:
                hours = 72
            # if it's saturday, wait 48
            elif now.isoweekday() == 6:
                hours = 48
            # if it's sunday-thur wait 24
            else:
                hours = 24

            future = now + timedelta(hours=hours)
            next_standup = datetime(future.year, future.month, future.day,
                                    standup_hour, standup_minute)

        return next_standup

    def save_schedule(self, connection):
        """
        Save all channel schedules to a file.
        """
        keys_to_save = ['time24h', 'ignoring']
        data = {}
        for channel in self.standup_schedules:
            data[channel] = {}
            for key in keys_to_save:
                data[channel][key] = self.standup_schedules[channel][key]

        data = {connection.id: data}
        with open('/home/jason/.warmachine/standup_schedules.json', 'w') as f:
            f.write(json.dumps(data))

        self.log.info('Schedules saved to disk')

    def load_schedule(self, connection):
        """
        Load the channel schedules from a file.
        """
        with open('/home/jason/.warmachine/standup_schedules.json', 'r') as f:
            try:
                data = json.loads(f.read())
            except Exception as e:
                self.log.debug('Error loading standup schedules: {}'.format(e))
                return

        for channel in data[connection.id]:
            self.schedule_standup(
                connection, channel, data[connection.id][channel]['time24h'])

            # Restore the ignore list
            try:
                self.standup_schedules[channel]['ignoring'] = \
                    data[connection.id][channel]['ignoring']
            except KeyError:
                pass
