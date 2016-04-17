import os
from os.path import join

import sqlite3
from database import NamelistItem

class ItemNotFoundError(Exception):
    def __init__(self, msg):
        Exception.__init__(self, msg)

class NoDatabaseError(Exception):
    def __init__(self, msg):
        Exception.__init__(self, msg)

INLIST_INDICES={
    'name': 0,
    'lower_name': 1,
    'dtype': 2,
    'default': 3,
    'dim': 4,
    'order': 5,
    'namelist': 6,
    'doc': 7
}

class CLI_Instance(object):
    def __init__(self):
        self._data = None
        self._names = None

    def _get_data(self):
        data_path = join(os.environ['MESA_DIR'], 'data')
        if 'inlist_commands.db' not in os.listdir(data_path):
            raise NoDatabaseError("No inlist command database found "
                                  "in {}.".format(data_path))
        return sqlite3.connect(join(data_path, 'inlist_commands.db')).cursor()

    def find_item(self, name):
        select_by = (name,)
        self.data.execute('SELECT * FROM inlist_items WHERE lower_name=?',
                          select_by)
        return NamelistItem.from_tuple(self.data.fetchone())
        # for namelist in self.data:
        #     try:
        #         i = self.names[namelist].index(name.lower())
        #         return self.data[namelist][i]
        #     except ValueError as e:
        #         pass
        # raise ItemNotFoundError('No such inlist item {} in any known ' +
        #     'namelist.'.format(name))

    def doc(self, name):
        return self.find_item(name).doc

    def default(self, name):
        return self.find_item(name).default

    @property
    def data(self):
        if self._data is None:
            self._data = self._get_data()
        return self._data

    @property
    def names(self):
        if self._names is None:
            self._names = {namelist: [item['lower_name'] for item in
                                      self.data[namelist]]
                           for namelist in self.data.keys()}
        return self._names