from .base import WarMachinePlugin


class StandUpPlugin(WarMachinePlugin):
    """
    WarMachine stand up plugin.

    Commands:
        !standup-add <24 hr time to kick off> <SunMTWThFSat> [channel]
        !standup-remove [channel]
    """
    async def recv_msg(self, connection, message):
        if not message['message'].startswith('!standup'):
            return

        self.log.debug('standup recv: {}'.format(message))

        cmd = message['message'].split(' ')[0]
        parts = message['message'].split(' ')[1:]

        if cmd == '!standup-add':
            await connection.say('Scheduling standup for {} on {}'.format(
                parts[1], parts[2]))

        # await connection.say('{}, {}'.format(cmd, parts), message['channel'])

    async def start_standup(self, connection):
        pass
