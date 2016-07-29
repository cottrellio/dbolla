import configparser


class Config(configparser.ConfigParser):
    def __init__(self, config_path=None):
        super().__init__()

        self.config_path = config_path

        if self.config_path:
            self.read(self.config_path)

    def options_as_dict(self, section):
        """
        Returns:
           dict: Dictionary of the options defined in this config
        """
        d = dict(self.items(section))
        d['section_name'] = section
        return d
