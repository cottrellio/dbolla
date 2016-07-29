import urllib.request
import json

from .base import WarMachinePlugin

__author__ = 'jason@zzq.org'
__class_name__ = 'GiphySearch'
__version__ = 1.0


class GiphySearch(WarMachinePlugin):
    async def recv_msg(self, connection, message):
        if message['message'].startswith('!giphy '):
            search_terms = ' '.join(message['message'].split(' ')[1:])

            self.log.debug('Searching giphy.com for: {}'.format(search_terms))

            url = ('http://api.giphy.com/v1/gifs/search?'
                   'q={}&api_key=dc6zaTOxFJmzC&limit=1'.format(
                       search_terms.replace(' ', '%20')))

            # TODO: This blocks
            req = urllib.request.Request(url)
            data = urllib.request.urlopen(req).read().decode('utf-8')

            data = json.loads(data)
            self.log.debug(data)
            try:
                result = data['data'][0]['images']['original']['url']
                await connection.say(result, message['channel'])
            except IndexError as e:
                await connection.say('No match for: {}'.format(search_terms),
                                     message['channel'])
