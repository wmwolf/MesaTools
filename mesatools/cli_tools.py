import os
from os.path import join

import yaml

class ItemNotFoundError(Exception):
    def __init__(self, msg):
        Exception.__init__(self, msg)

class NoDatabaseError(Exception):
    def __init__(self, msg):
        Exception.__init__(self, msg)

class CLI_Instance(object):
    def __init__(self):
        self._data = None
        self._names = None

    def _get_data(self):
        data_path = join(os.environ['MESA'], 'data')
        if 'inlist_commands.yml' not in os.listdir(data_path):
            raise NoDatabaseError("No inlist command database found "
                                  "in {}.".format(data_path))
        return yaml.load(join(data_path, 'inlist_commands.yml'))

    def find_item(self, name):
        for namelist in self.data:
            try:
                i = self.names[namelist].index(name.lower())
                return self.data[namelist][i]
            except ValueError as e:
                pass
        raise ItemNotFoundError('No such inlist item {} in any known ' +
            'namelist.'.format(name))

    def doc(self, name):
        return self.find_item(name).doc

    @property
    def data(self):
        if self._data is None:
            self._data = self._get_data()
        return self._data

    @property
    def names(self):
        if self._names is None:
            self._names = {namelist: [item.lower_name for item in self.data[
                namelist]] for namelist in self.data}
        return self._names