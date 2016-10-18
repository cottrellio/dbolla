INITALIZED = 'Initalized'
CONNECTED = 'Connected'
CONNECTING = 'Connecting'


class Connection(object):
    def __init__(self):
        self.config_dir = None

    def connect(self, *args, **kwargs):
        """
        This is called by the main start method. It should prepare your
        Connection and connect.
        """
        raise NotImplementedError('{} must implement `connect` method'.format(
            self.__class__.__name__))

    def read(self):
        """
        Dictionary of data in the following format:
        {
          'sender': 'username/id',
          'channel': 'channel name' or None,
          'message': 'actual message',
        }

        Returns:
            dict: Data from the connection that the bot should consider.
        """
        raise NotImplementedError('{} must implement `read` method'.format(
            self.__class__.__name__))

    def id(self):
        """
        Unique ID for this connection. Since there can be more than one
        connection it should be unique per actual connection to the server. For
        example `bot nickname` + `server host:port`. This is used to store
        settings and other information.

        Returns:
           str: Unique ID for this connection object
        """
        raise NotImplementedError('{} must implement `id` method'.format(
            self.__class__.__name__))

    def say(self, message, destination):
        """
        Async method that a plugin can use to send a message to a channel or user.
        """
        raise NotImplementedError('{} must implement `say` method'.format(
            self.__class__.__name__))
