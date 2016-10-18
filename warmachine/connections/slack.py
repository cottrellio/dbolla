import asyncio
import json
import logging
from pprint import pformat
from urllib.parse import urlencode
import urllib.request
import sys

import websockets

from .base import Connection, INITALIZED, CONNECTED
from ..utils.decorators import memoize

#: Define slack as a config section prefix
__config_prefix__ = 'slack'


class SlackWS(Connection):
    def __init__(self, options, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._loop = asyncio.get_event_loop()
        self.log = logging.getLogger(self.__class__.__name__)
        self.host = None
        self.token = options['token']

        self._info = None
        self.reconnect_url = ''

        self.channel_map = {}  # channel and im info keyed by the slack id
        self.channel_name_to_id = {} # slack channel/group name mapped to the id
        self.user_map = {}     # user info keyed by their slack id
        self.user_nick_to_id = {}  # slack user id mapped to the (nick)name

        self.my_id = '000'

        self.ws = None
        # used to give messages an id. slack requirement
        self._internal_msgid = 0

        self.status = INITALIZED

    @property
    @memoize
    def id(self):
        from hashlib import md5
        return md5(self.token.encode()).hexdigest()

    async def connect(self):
        try:
            self.host = self.authenticate()
        except Exception:
            self.log.exception('Error authenticating to slack')
            return
        self.log.info('Connecting to {}'.format(self.host))
        self.ws = await websockets.connect(self.host)
        self.STATUS = CONNECTED

        return True

    async def read(self):
        if self.ws:
            try:
                message = json.loads(await self.ws.recv())
            except websockets.ConnectionClosed as e:
                self.log.error('{}'.format(e))
                while not await self.connect():
                    self.error('Trying to reconnect...')
                    await asyncio.sleep(300)
                return
            # Slack is acknowledging a message was sent. Do nothing
            if 'reply_to' in message:
                # {'ok': True,
                #  'reply_to': 1,
                #  'text': "['!whois', 'synic']",
                #  'ts': '1469743355.000150'}
                self.log.debug('Ignoring reply_to message: {}'.format(
                    message))
                return

            # Sometimes there isn't a type in the message we receive
            if 'type' not in message:
                self.log.error('Received typeless message: {}'.format(message))
                return

            if message['type'] == 'message' and 'subtype' not in message:
                # Handle text messages from users
                return await self.process_message(message)
            else:
                if 'subtype' in message:
                    # This is a message with a subtype and should be processed
                    # differently
                    msgtype = '{}_{}'.format(
                        message['type'], message['subtype'])
                else:
                    # This is a non-message event from slack.
                    # https://api.slack.com/events
                    msgtype = message['type']

                # Look for on_{type} methods to pass the dictionary to for
                # additional processing
                func_name = 'on_{}'.format(msgtype)
                if hasattr(self, func_name):
                    getattr(self, func_name)(message)
                else:
                    self.log.debug('{} does not exist for message: {}'.format(
                        func_name, message))

    async def say(self, message, destination):
        """
        Say something in the provided channel or IM by id
        """
        # If the destination is a user, figure out the DM channel id
        if destination and destination.startswith('#'):
            destination = self.channel_name_to_id[destination.replace('#','')]
        else:
            _user = self.user_nick_to_id[destination]

            if '#' not in destination and 'is_bot' not in self.user_map[_user]:
                self.log.error('is_bot property not found for user {}'.format(
                    destination))

            # slack doesn't allow bots to message other bots
            if '#' not in destination and (self.user_map[_user]['deleted'] or \
                                           self.user_map[_user]['is_bot']):
                return

            destination = self.get_dm_id_by_user(_user)

        self._internal_msgid += 1
        message = {
            'id': self._internal_msgid,
            'type': 'message',
            'channel': destination,
            'text': str(message)
        }
        self.log.debug("Saying {}".format(message))
        await self._send(json.dumps(message))

    async def _send(self, message):
        """
        Send ``message`` to the connected slack server
        """
        await self.ws.send(message)

    def authenticate(self):
        """
        Populate ``self._info``

        Returns:
            str: websocket url to connect to
        """
        url = 'https://slack.com/api/rtm.start?{}'.format(
            urlencode(
                {'token':
                 self.token}))
        self.log.debug('Connecting to {}'.format(url))
        req = urllib.request.Request(url)

        r = urllib.request.urlopen(req).read().decode('utf-8')
        self._info = json.loads(r)

        if not self._info.get('ok', True):
            raise Exception('Slack Error: {}'.format(
                self._info.get('error', 'Unknown Error')))

        # Slack returns a huge json struct with a bunch of information
        self.process_connect_info(self._info)

        self.log.debug('Got websocket url: {}'.format(self._info.get('url')))
        return self._info.get('url')

    def process_connect_info(self, info):
        """
        Processes the connection info provided by slack
        """
        # If there is nothing to process then return
        if not info:
            return

        # Save the bot's id
        try:
            self.my_id = self._info['self'].get('id', '000')
            self.nick = self._info['self'].get('name', None)
        except KeyError:
            self.log.error('Unable to read self section of connect info')

        # Map users
        for u in self._info.get('users', []):
            self.user_map[u['id']] = u
            self.user_nick_to_id[u['name']] = u['id']

        # Map IM
        for i in self._info.get('ims', []):
            self.channel_map[i['id']] = i

        # Map Channels
        for c in self._info.get('channels', []):
            self.channel_map[c['id']] = c
            self.channel_name_to_id[c['name']] = c['id']

        for g in self._info.get('groups', []):
            self.channel_map[g['id']] = g
            self.channel_name_to_id[g['name']] = g['id']

    async def process_message(self, msg):
        if 'text' not in msg:
            self.log.error('key "text" not found in message: {}'.format(msg))

        # Built-in !whois command. Return information about a particular user.
        if msg['text'].startswith('!whois'):
            nicknames = msg['text'].split(' ')[1:]
            for n in nicknames:
                await self.say(pformat(self.user_map[self.user_nick_to_id[n]]),
                               msg['channel'])
            return

        # Map the slack ids to usernames and channels/groups names
        user_nickname = self.user_map[msg['user']]['name']
        if msg['channel'].startswith('D'):
            # This is a private message
            channel = None
        else:
            try:
                channel = '#{}'.format(self.channel_map[msg['channel']]['name'])
            except KeyError:
                channel = None

        retval = {
            'sender': user_nickname,
            'channel': channel,
            'message': msg['text']
        }
        return retval

    def on_user_change(self, msg):
        """
        The user_change event is sent to all connections for a team when a team
        member updates their profile or data. Clients can use this to update
        their local cache of team members.

        https://api.slack.com/events/user_change
        """
        user_info = msg['user']

        self.user_map[user_info['id']] = user_info

        # Update the nick mapping if the user changed their nickname
        try:
            old_nick = self.user_map[user_info['id']]['nick']
        except KeyError as e:
            old_nick = None

        if old_nick and old_nick != user_info['nick']:
            del self.user_nick_to_id[old_nick]
            self.user_nick_to_id[user_info['nick']] = user_info['id']

    def on_reconnect_url(self, msg):
        """
        The reconnect_url event is currently unsupported and experimental.

        https://api.slack.com/events/reconnect_url
        """
        # self.reconnect_url = msg['url']
        # self.log.debug('updated_reconnect_url: {}'.format(self.reconnect_url))

    def on_presence_change(self, msg):
        """
        updates user's presence in ``self.user_map``
        """
        try::
            self.log.debug('updated_presence: {} ({}) was: {} is_now: {}'.format(
                msg['user'], self.user_map[msg['user']]['name'],
                self.user_map[msg['user']].get('presence', '<undefined>'),
                msg['presence']
            ))
            self.user_map[msg['user']]['presence'] = msg['presence']
        except KeyError:
            pass

    @memoize  # the dm id should never change
    def get_dm_id_by_user(self, user_id):
        """
        Return the channel id for a direct message to a specific user.

        Args:
            user_id (str): slack user id

        Return:
            str: DM channel id for the provided user.  None on error
        """
        url = 'https://slack.com/api/im.open?{}'.format(urlencode({
            'token': self.token,
            'user': user_id,
        }))

        req = urllib.request.Request(url)
        r = urllib.request.urlopen(req).read().decode('utf-8')

        data = json.loads(r)

        if not data['ok']:
            self.log.error(data)
            return

        return data['channel']['id']

    def get_users_by_channel(self, channel):
        channel = self.channel_name_to_id[channel.replace('#', '')]

        if channel.startswith('G'):
            key = 'group'
        elif channel.startswith('C'):
            key = 'channel'
        else:
            return

        url = 'https://slack.com/api/{}s.info?{}'.format(
            key, urlencode(
            {
                'token': self.token,
                'channel': channel,
            }))

        self.log.debug('Gathering list of users for channel {} from: {}'.format(
            channel, url))
        req = urllib.request.Request(url)
        r = json.loads(urllib.request.urlopen(req).read().decode('utf-8'))

        users = []
        for u_id in r[key]['members']:
            users.append(self.user_map[u_id]['name'])

        return users

    async def on_group_join(self, channel):
        """
        The group_joined event is sent to all connections for a user when that
        user joins a private channel. In addition to this message, all existing
        members of the private channel will receive a group_join message event.

        https://api.slack.com/events/group_joined
        """
        # {
        #     'channel': {
        #         'members': ['U0286NL58', 'U1U05AF5J'],
        #         'id': 'G1W837CGP',
        #         'is_group': True,
        #         'is_archived': False,
        #         'latest': {
        #             'user': 'U0286NL58',
        #             'subtype': 'group_join',
        #             'ts': '1469746594 .000002',
        #             'type': 'message',
        #             'text': '<@U0286NL58|jason> has joined the group'
        #         },
        #         'is_mpim': False,
        #         'unread_count': 0,
        #         'purpose': {
        #             'creator': '',
        #             'value': '',
        #             'last_set': 0
        #         },
        #         'is_open': True,
        #         'topic': {
        #             'creator': '',
        #             'value': '',
        #             'last_set': 0
        #         },
        #         'creator': 'U0286NL58',
        #         'unread_count_display': 0,
        #         'name': 'wm-test',
        #         'last_read': '1469746594.000002',
        #         'created': 1469746594
        #     },
        #     'type': 'group_joined'
        # }

    def on_message_message_changed(self, msg):
        """
        A message_changed message is sent when a message in a channel is edited
        using the chat.update method. The message property contains the updated
        message object.

        When clients receive this message type, they should look for an
        existing message with the same message.ts in that channel. If they
        find one the existing message should be replaced with the new one.

        https://api.slack.com/events/message/message_changed
        """
        # {
        #     'hidden': True,
        #     'event_ts': '1469748743.218081',
        #     'subtype': 'message_changed',
        #     'message': {
        #         'attachments': [{
        #             'id': 1,
        #             'image_width': 800,
        #             'fallback': '800x450px image',
        #             'from_url':
        # 'http://media1.giphy.com/media/3o85fPE3Irg8Wazl9S/giphy.gif',
        #             'image_bytes': 4847496,
        #             'image_url':
        # 'http://media1.giphy.com/media/3o85fPE3Irg8Wazl9S/giphy.gif',
        #             'image_height': 450,
        #             'is_animated': True
        #         }],
        #         'type': 'message',
        #         'ts': '1469748743.000019',
        #         'text':
        # '<http://media1.giphy.com/media/3o85fPE3Irg8Wazl9S/giphy.gif>',
        #         'user': 'U1U05AF5J'
        #     },
        #     'channel': 'G1W837CGP',
        #     'ts': '1469748743.000020',
        #     'type': 'message',
        #     'previous_message': {
        #         'type': 'message',
        #         'ts': '1469748743.000019',
        #         'text':
        # '<http://media1.giphy.com/media/3o85fPE3Irg8Wazl9S/giphy.gif>',
        #         'user': 'U1U05AF5J'
        #     }
        # }

        def on_reaction_added(self, msg):
            """
            When someone adds a reaction to a message
            """

# Invited to a public channel
#     2016-07-29 16:23:24,817 [DEBUG] SlackWS: on_channel_joined does not exist for message: {'type': 'channel_joined', 'chan
# nel': {'members': ['U0286NL58', 'U1U05AF5J'], 'purpose': {'last_set': 0, 'creator': '', 'value': ''}, 'topic': {'last_s
# et': 0, 'creator': '', 'value': ''}, 'is_member': True, 'is_channel': True, 'creator': 'U0286NL58', 'is_archived': Fals
# e, 'unread_count_display': 0, 'id': 'C1WJU3ZU0', 'name': 'wm-test2', 'is_general': False, 'created': 1469830985, 'unrea
# d_count': 0, 'latest': {'text': '<@U0286NL58|jason> has joined the channel', 'type': 'message', 'user': 'U0286NL58', 's
# ubtype': 'channel_join', 'ts': '1469830985.000002'}, 'last_read': '1469830985.000002'}}
# 2016-07-29 16:23:24,878 [DEBUG] SlackWS: on_message_channel_join does not exist for message: {'channel': 'C1WJU3ZU0', '
# text': '<@U1U05AF5J|wm-standup-test> has joined the channel', 'type': 'message', 'inviter': 'U0286NL58', 'subtype': 'ch
# annel_join', 'user_profile': {'real_name': '', 'name': 'wm-standup-test', 'image_72': 'https://avatars.slack-edge.com/2
# 016-07-21/62015427159_1da65a3cf7a85e85c3cb_72.png', 'first_name': None, 'avatar_hash': '1da65a3cf7a8'}, 'ts': '14698310
# 04.000003', 'user': 'U1U05AF5J', 'team': 'T027XPE12'}

# Someone else joins a public channel
# 2016-07-29 16:26:19,966 [DEBUG] SlackWS: on_message_channel_join does not exist for message: {'type': 'message', 'invit
# er': 'U0286NL58', 'ts': '1469831179.000004', 'team': 'T027XPE12', 'user': 'U0286167T', 'channel': 'C1WJU3ZU0', 'user_pr
# ofile': {'name': 'synic', 'image_72': 'https://avatars.slack-edge.com/2016-06-24/54136624065_49ec8bc368966c152817_72.jp
# g', 'real_name': 'Adam Olsen', 'first_name': 'Adam', 'avatar_hash': '49ec8bc36896'}, 'subtype': 'channel_join', 'text':
#  '<@U0286167T|synic> has joined the channel'}

# Invited to a private channel
# 2016-07-29 16:27:29,376 [DEBUG] SlackWS: on_message_group_join does not exist for message: {'type': 'message', 'inviter
# ': 'U0286NL58', 'ts': '1469831249.000047', 'team': 'T027XPE12', 'user': 'U0286167T', 'channel': 'G1W837CGP', 'user_prof
# ile': {'name': 'synic', 'image_72': 'https://avatars.slack-edge.com/2016-06-24/54136624065_49ec8bc368966c152817_72.jpg'
# , 'real_name': 'Adam Olsen', 'first_name': 'Adam', 'avatar_hash': '49ec8bc36896'}, 'subtype': 'group_join', 'text': '<@
# U0286167T|synic> has joined the group'}
