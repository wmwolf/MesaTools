import os
from os.path import join

import sqlite3
from database import NamelistItem, make_database

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
        data_path = join(os.environ['MESA_DIR'], 'data')
        if 'inlist_commands.db' not in os.listdir(data_path):
            raise NoDatabaseError("No inlist command database found "
                                  "in {}.".format(data_path))
        return sqlite3.connect(join(data_path, 'inlist_commands.db')).cursor()

    def find_item(self, name):
        select_by = (name.lower(),)
        self.data.execute('SELECT * FROM inlist_items WHERE lower_name=?',
                          select_by)
        return NamelistItem.from_tuple(self.data.fetchone())

    def search_name(self, name, namelist=None):
        search_pattern = '%{}%'.format(name.lower())
        if namelist is None:
            injection = (search_pattern, )
            self.data.execute('SELECT * FROM inlist_items WHERE lower_name ' +
                              'LIKE ?', injection)
        else:
            injection = (namelist, search_pattern)
            self.data.execute('SELECT * FROM inlist_items WHERE lower_name ' +
                              'LIKE ? AND namelist=?', injection)
        names = [NamelistItem.from_tuple(item).name for item in
                 self.data.fetchall()]
        return '\n'.join(names)

    def search_doc(self, term, namelist=None):
        search_pattern = '%{}%'.format(term)
        if namelist is None:
            injection = (search_pattern, )
            self.data.execute('SELECT * FROM inlist_items WHERE doc ' +
                              'LIKE ?', injection)
        else:
            injection = (namelist, search_pattern)
            self.data.execute('SELECT * FROM inlist_items WHERE doc ' +
                              'LIKE ? AND namelist=?', injection)
        output = []
        for item in self.data.fetchall():
            data = NamelistItem.from_tuple(item)
            output.append("{}\n{}\n".format(data.name, data.doc)+('-'*78))
        return '\n'.join(output)

    def doc(self, name):
        return self.find_item(name).doc

    def default(self, name):
        return self.find_item(name).default

    def dtype(self, name):
        return self.find_item(name).dtype

    def namelist(self, name):
        return self.find_item(name).namelist

    def summary(self, name):
        item = self.find_item(name)
        res = ("name:     {}\n".format(item.name) +
               "dtype:    {}\n".format(item.dtype) +
               "default:  {}\n".format(item.default) +
               "namelist: {}\n".format(item.namelist) +
               "doc:      \n\n{}".format(item.doc))
        return res

    def mesa_dir(self):
        return os.environ['MESA_DIR']

    def version(self):
        with open(join(self.mesa_dir(), 'data', 'version_number'), 'r') as f:
            ver_num = f.read().strip()
        return int(ver_num)

    def makedb(self, savefile=None):
        make_database(savefile)


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