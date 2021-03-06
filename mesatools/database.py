from os.path import join, isfile, splitext
import os
import re
import shutil
import sqlite3

from .helpers import get_mesa_dir
from .fortran import f_end, full_lines


# Each item has an associated converter function that will take inputs
# and cast them to the appropriate data types.
dtype_funcs = {
    'bool': bool,
    'str': str,
    'int': int,
    'float': float
}

# Used to convert between fortran and python type names
dtypes = {
    'logical': 'bool',
    'character': 'str',
    'integer': 'int',
    'real': 'float',
    'type': 'bool'
}

# Bare-bones defaults for inlist items of each data type, should be
# overwritten by reading from defaults files
dfts = {
    'bool': False,
    'str': '',
    'int': 0,
    'float': 0.0
}


class NamelistItem(object):
    """Container for MESA namelist item.

    Parameters
    ----------
    name : str
        name of the namelist item, case sensitive
    dtype : string
        data type of the namelist item, should be 'str', 'bool', 'int', or
        'float'
    dim : int
        dimension of the data type. Typically 0 for scalars, but may be 1 or
        2 for vector data
    order : int
        position of the namelist item in its defaults file
    namelist : str
        name of the namelist that the item belongs to
    doc : str
        documentation string from defaults file of the object

    Attributes
    ----------
    name : str
        name of the namelist item, case sensitive
    lower_name : str
        same as `name`, but all in lower case for consistency
    dtype : function
        data type of the namelist item, should be str, bool, int, or float
    default : bool, str, float, or int
        default value of item
    dim : int
        dimension of the data type. Typically 0 for scalars, but may be 1 or
        2 for vector data
    order : int
        position of the namelist item in its defaults file
    namelist : str
        name of the namelist that the item belongs to
    doc : str
        documentation string from defaults file of the object
    """

    def __init__(self, name, dtype, default, dim, order, namelist, doc):
        self.name = name
        self.lower_name = name.lower()
        self.dtype = dtype
        self.default = default
        self.dim = dim
        self.order = order
        self.namelist = namelist
        self.doc = doc

    @classmethod
    def from_tuple(cls, tup):
        '''Make new InlistItem from tuple produced by `to_tuple`'''
        name = tup[0]
        dtype = tup[2]
        default = tup[3]
        dim = tup[4]
        order = tup[5]
        namelist = tup[6]
        doc = tup[7]
        if dtype == 'bool':
            if default == "False":
                default = False
            else:
                default = True
        else:
            try:
                default = dtype_funcs[dtype](default)
            except KeyError as e:
                print("Trying to find dtype function for dtype: {}".format(
                    dtype))
                print("From tuple: {}".format(tup))
                print("From tuple type: {}".format(type(tup)))
                raise e
        return cls(name, dtype, default, dim, order, namelist, doc)

    def to_dict(self):
        return {'name': self.name, 'lower_name': self.lower_name, 'dtype':
                self.dtype, 'default': self.default, 'dim': self.dim, 'order':
                self.order, 'namelist': self.namelist, 'doc': self.doc}

    def to_tuple(self):
        return (self.name, self.lower_name, self.dtype, str(self.default),
                self.dim, self.order, self.namelist, self.doc)


class BadPathError(Exception):
    def __init__(self, msg):
        Exception.__init__(self, msg)


class InvalidDatabaseError(Exception):
    def __init__(self, msg):
        Exception.__init__(self, msg)


def dtype_and_value(val_string):
    '''Determine data type and appropriate value of value in string form.

    Figures out if the value represented in a string is most likely a boolean,
    string, floating point number, or integer given its string representation.
    Then returns the data type (as a function) as well as the actual value
    that has been caste by the data type function.

    Parameters
    ----------
    val_string : str
        the string that is to be analyzed

    Returns
    -------
    str : the function name used to cast the string into its value
    bool, str, float, or int : value obtained from casting the string

    Notes
    -----
    If the data type cannot be guessed through the fairly loose criteria given
    here, it will be preserved as a string and a warning will be printed.
    '''
    if val_string.lower() in ['.true.', '.false.']:
        dtype = 'bool'
        if val_string.lower() == '.true.':
            val = True
        else:
            val = False
    elif "'" in val_string.lower():
        dtype = 'str'
        val = val_string
    elif (('d' in val_string.lower()) or ('.' in val_string.lower()) or
          ('e' in val_string.lower())):
        dtype = 'float'
        val = val_string.lower().replace('d', 'e')
    elif re.match('\A-?\d+\Z', val_string.lower()):
        dtype = 'int'
        val = val_string
    else:
        print("Couldn't determine dtype of " +
              val_string + '. Keeping it as a string ' +
              'literal.')
        dtype = 'str'
        val = val_string
    val = dtype_funcs[dtype](val)
    return dtype, val


def get_doc_text(defaults_lines, name):
    """Get full doc text for an inlist item."""
    def is_doc(line):
        blank_matcher = re.compile('\s*\Z')
        text_matcher = re.compile('\s*!\s*[^#]\w+')
        return ((blank_matcher.match(line) or text_matcher.match(line)) is not
                None)

    def is_code(line):
        code_matcher = re.compile('\s*\w+')
        return code_matcher.match(line) is not None

    header_matcher = re.compile('\A\s*!\s*###\s*{}(\(.*\))?\s*\Z'.format(name))
    res = ''
    # print("Getting documentation for {}".format(name))
    found_header = False
    for i, line in enumerate(defaults_lines):
        if header_matcher.match(line) is not None:
            res += (line.strip() + "\n")
            found_header = True
        elif found_header:
            if is_code(line):
                # print("CODE LINE: {}".format(line))
                # print("reached end!")
                # print(res.strip())
                return res.strip()
            elif is_doc(line):
                res += ('  ' + line.strip() + '\n')
    # print("Never found the end.\n")
    return "Could not get documentation for item {}.".format(name)


def generate_language_data(mesa_dir=None):
    """Make list of InlistItems that characterizes all valid inlist commands.

    Parameters
    ----------
    mesa_dir : str, optional
        path to mesa installation from which to generate language, default is
        taken from environment variable MESA_DIR
    """

    # Confirm/find mesa directory
    mesa_dir = get_mesa_dir(mesa_dir)

    # Determine mesa version for use in determining file names
    with open(join(mesa_dir, 'data', 'version_number'), 'r') as f:
        version = int(f.readline())

    # Just do basic mesa star namelists now,
    # should be able to add support for binary, others easily, though
    # maybe through external configuration file that specifies namelist names
    # and associated definition and default files?
    namelists = ['star_job', 'controls', 'pgstar']

    # Each namelist has two types of files (and possibly multiple instances of
    # these files). The first are the definition files, which establish the
    # variable name, type, and shape. The defaults files then specify the
    # assumed default values of these items, provide a natural order for them
    # to appear in an inlist, as well document their utility. While we can
    # function without the default file, it is not desirable, mostly for the
    # ordering functionality (inlists will be jumbled).
    define_files = {
        'star_job': [join(mesa_dir, 'star', 'private',
                          'star_job_controls.inc')],
        'controls': [join(mesa_dir, 'star', 'private', 'star_controls.inc')],
        'pgstar': [join(mesa_dir, 'star', 'private', 'pgstar_controls.inc')]
    }
    define_files['controls'].append(join(mesa_dir, 'star', 'private',
                                         'ctrls_io.{}'.format(f_end(version))))
    default_files = {namelist: join(mesa_dir, 'star', 'defaults', namelist +
                                    '.defaults') for namelist in namelists}

    # Useful regular expressions used elsewhere downscope
    dimension_match = re.compile('dimension\((.*)\)', re.IGNORECASE)
    paren_matcher = re.compile('\(.*\)')

    # Go through each namelist, pulling information with associated
    # definition and default files and buliding a dict of arrays of inlist
    # items.
    namelist_data = []
    for namelist in namelists:
        print("Gathering inlist items for namelist {}...".format(namelist))
        for define_file in define_files[namelist]:
            try:
                with open(define_file, 'r') as f:
                    lines = f.readlines()
            except IOError as e:
                print("Couldn't open file {}.".format(define_file))
                continue

            # Get full lines with no comments (inline or otherwise) or blank
            # lines
            code_lines = full_lines(lines, include_blanks=False,
                                    include_comments=False)
            code_lines = [line[0:line.index('!')].strip() if '!' in line else
                          line.strip() for line in code_lines]

            assignment_lines = []
            for i, line in enumerate(code_lines):
                if re.match('\A\s*contains', line):
                    break
                if '::' not in line:
                    continue
                else:
                    assignment_lines.append(line)

            # Break each full line into pairs of declaration information (
            # type, dimension, etc.) and names (one or more separated by
            # commas), ascertaining the type, dimension, and default value of
            # each variable.
            pairs = [[s.strip() for s in line.split('::')] for line in
                     assignment_lines]
            for this_type, names in pairs:
                if 'logical' in this_type:
                    dtype = dtypes['logical']
                elif 'character' in this_type:
                    dtype = dtypes['character']
                elif 'integer' in this_type:
                    dtype = dtypes['integer']
                elif 'real' in this_type:
                    dtype = dtypes['real']
                else:
                    dtype = dtypes['character']
                dft = dfts.get(dtype, '')
                name_chars = list(names)

                # Iterate through names and keep track of which have
                # dimension greater than 1 (names ending with parentheticals
                # with zero or more commas) and those that have dimension 0 (
                # no parentheses at all. Compute dimension by either counting
                # commas in parentheticals or in the DIMENSION keyword
                new_names = []
                paren_level = 0
                for char in name_chars:
                    if paren_level > 0 and char == ',':
                        new_names.append('!')
                        continue
                    elif char == '(':
                        paren_level += 1
                    elif char == ')':
                        paren_level -= 1
                    new_names.append(char)
                new_names = (''.join(new_names).split(','))
                for name in new_names:
                    if re.match('\(.*\)', name):
                        num_indices = name.count('!') + 1
                        name = re.sub('\(.*\)', '')
                    elif dimension_match.match(this_type):
                        dim_match = dimension_match.match(this_type)
                        num_indices = dim_match.groups()[0].count(',') + 1
                    else:
                        num_indices = 0
                    name = paren_matcher.sub('', name)
                    # print("Adding inlist item {}".format(name.strip()))

                    # Add new record for namelist item, which will later be
                    # checked for more proper defaults, order,
                    # and documentation.
                    namelist_data.append(NamelistItem(name.strip(),
                                                      dtype, dft, num_indices,
                                                      -1, namelist, ''))
        default_file = default_files[namelist]
        # Read in lines from default files. If that fails, fail gracefully
        # and try opening the next one.
        try:
            with open(default_file, 'r') as f:
                lines = f.readlines()
        except IOError as e:
            print("Couldn't open file {}.".format(default_file))
            continue

        # Get all names for items in this namelist
        names = [item.name for item in namelist_data]
        lower_names = [name.lower() for name in names]

        # Go through each line of the defaults file, looking for lines that
        # define the default for a control. Then name, order, dtype and
        # default from its position and value in the file.
        order = 0
        for i, line in enumerate(lines):
            # only look at lines that AREN'T comments or blank lines
            if re.match('\A\s*\!', lines[i]) or re.match('\A\s+\Z',
                                                         lines[i]):
                continue
            else:
                # split definition line around equals sign
                # print("Processing line " + lines[k])
                def_line = lines[i].split('=')
                # get name and see if it has any indices
                assign_name = def_line[0]
                if paren_matcher.match(assign_name):
                    num_indices = assign_name.count(',')
                else:
                    num_indices = 0
                assign_name = paren_matcher.sub('', assign_name).strip()
                # get default value in string form
                val_string = def_line[1].strip()
                if '!' in val_string:
                    val_string = val_string[:val_string.index(
                        '!')].strip()
                dtype, val = dtype_and_value(val_string)
                doc = get_doc_text(lines, assign_name)

                # find inlist item and update metadata
                try:
                    j = lower_names.index(assign_name.lower())
                    namelist_data[j].default = val
                    namelist_data[j].order = order
                    namelist_data[j].doc = doc
                except ValueError as e:
                    namelist_data.append(NamelistItem(assign_name,
                                                      dtype, val, num_indices,
                                                      order, namelist, doc))
                order += 1
        # namelist_dicts = [item.to_dict() for item in namelist_data]
        namelist_tuples = [item.to_tuple() for item in namelist_data]
    return namelist_tuples


def make_database(save_file=join(get_mesa_dir(), 'data', 'mesa.db')):
    '''Make database of inlist commands.

    Parameters
    ----------
    save_file : str, optional
        path to database file that should hold language information, default is
        `$MESA_DIR/data/mesa.db`

    Returns
    -------
    None
    '''
    data = generate_language_data(mesa_dir=get_mesa_dir())
    print(data)

    # Make SQlite3 table
    conn = sqlite3.connect(save_file)
    c = conn.cursor()
    c.execute("CREATE TABLE inlist_items\n" + "(name text, lower_name text, "
              "dtype text, dft text, dim integer, ord integer, namelist " +
              "text, doc text)")
    conn.commit()

    # Add data
    c.executemany('INSERT INTO inlist_items VALUES (?,?,?,?,?,?,?,?)', data)
    conn.commit()


def have_database():
    return 'mesa.db' in os.listdir(join(get_mesa_dir(), 'data'))


class MesaDatabase(object):
    '''Interface for reading and searching a MESA database.

    Parameters
    ----------
    db_file : str, optional
        path to MESA database file. If none is provided, looks in
        $MESA_DIR/data/mesa.db

    Attributes
    ----------
    db_file : str
        path to MESA database file
    cursor : sqlite.Cursor
        database cursor for reading from database
    '''

    def __init__(self, db_file=None):
        if db_file is None:
            db_file = join(get_mesa_dir(), 'data', 'mesa.db')
        self._db_file = db_file
        self._cursor = None

    def create(self):
        """Backs up old database if it is present and makes new database."""
        if self._does_db_file_exist():
            name, ext = splitext(self.db_file)
            old_db_file = ''.join((name + '_old', ext))
            shutil.move(self.db_file, old_db_file)
        make_database(self.db_file)

    def search(self, table, query, terms):
        '''Generic search on the database cursor.

        Modifies the state of `self.cursor` so that search results can be
        read off

        Parameters
        ----------
        table : str
            name of the table in the database to be queried
        query : str
            SQL query with number of ?'s matching the length of `terms`
        terms : tuple of str
            terms to be sanitized and injected in to `query`. Must be same
            length as the number of ?'s in `query`.

        Returns
        -------
        None
        '''
        self._ensure_connection()
        assert query.count('?') == len(terms), ("Search query must have " +
                                                "equal number of question " +
                                                "marks as the length of " +
                                                "search terms.")
        self.cursor.execute("SELECT * FROM {} WHERE {}".format(table, query),
                            terms)

    def search_for_one(self, table, query, terms):
        """Perform search AND return first result.
        Parameters
        ----------
        table : str
            name of the table in the database to be queried
        query : str
            SQL query with number of ?'s matching the length of `terms`
        terms : tuple of str
            terms to be sanitized and injected in to `query`. Must be same
            length as the number of ?'s in `query`.

        Returns
        -------
        tuple :
            Tuple of length one with first database search result
        """
        self.search(table, query, terms)
        return self.cursor.fetchone()

    def search_for_many(self, table, query, terms):
        """Perform search AND return results.
        Parameters
        ----------
        table : str
            name of the table in the database to be queried
        query : str
            SQL query with number of ?'s matching the length of `terms`
        terms : tuple of str
            terms to be sanitized and injected in to `query`. Must be same
            length as the number of ?'s in `query`.

        Returns
        -------
        tuple :
            Tuple of all database search results
        """
        self.search(table, query, terms)
        return self.cursor.fetchall()

    def _ensure_connection(self):
        '''Connects to database if not already done.'''
        if self.cursor is None:
            self._connect()

    def _connect(self):
        '''Establish connection to database and make cursor.'''
        if self._does_db_file_exist():
            conn = sqlite3.connect(self.db_file)
            self.cursor = conn.cursor()
        else:
            raise InvalidDatabaseError('No such database found: {}'.format(
                self.db_file))

    def _does_db_file_exist(self):
        '''Determines if database file exists or not.'''
        return isfile(self.db_file)

    @property
    def db_file(self):
        return self._db_file

    @property
    def cursor(self):
        return self._cursor

    @cursor.setter
    def cursor(self, value):
        self._cursor = value


class InlistDbHandler(object):
    """Interface to get data from inlist commands section of a mesa database.

    Parameters
    ----------
    mesa_db : mesatools.MesaDatabase
        Database that contains table 'inlist_items'

    Attributes
    ----------
    db : mesatools.MesaDatabase
        the database object that is queried"""

    def __init__(self, mesa_db):
        self._db = mesa_db
        self._data = None

    def find_namelist_item(self, name):
        """Search through inlist_items for namelist object and return one

        Parameters
        ----------
        name : str
            name of the namelist item to be searched for; case insensitive

        Returns
        -------
        mesatools.database.NamelistItem
            Container for data about the desired NameList Item

        Notes
        -----
        Unclear what this returns if namelist item is not found.
        """
        injection = (name.lower(),)
        return NamelistItem.from_tuple(
            self.db.search_for_one('inlist_items', 'lower_name=?', injection))

    def search_namelist_name(self, name, namelist=None):
        """Searches for namelist items whose names contain a certain string.

        Parameters
        ----------
        name : str
            name or part of name to be searched for
        namelist : str, optional
            name of a namelist to restrict search to (ex. star_job, controls,
            or pgstar. Defaults to None, which means search all namelists

        Returns
        -------
        list of mesatools.database.NamelistItem
            all namelist items that have `name` somewhere in their name and
            belong to `namelist`, if provided
        """
        search_pattern = '%{}%'.format(name.lower())
        if namelist is None:
            injection = (search_pattern,)
            query = 'lower_name LIKE ?'
        else:
            injection = (namelist, search_pattern)
            query = 'lower_name LIKE ? AND namelist=?'
        return [NamelistItem.from_tuple(item) for item in
                self.db.search_for_many('inlist_items', query, injection)]

    def search_doc(self, term, namelist=None):
        """Searches for namelist items by terms in their documentation.

        Parameters
        ----------
        term : str
            term for which to look in documentation for
        namelist : str, optional
            name of a namelist to restrict search to (ex. star_job, controls,
            or pgstar. Defaults to None, which means search all namelists

        Returns
        -------
        list of mesatools.database.NamelistItem
            all namelist items that have `name` somewhere in their name and
            belong to `namelist`, if provided
        """
        search_pattern = '%{}%'.format(term)
        if namelist is None:
            injection = (search_pattern,)
            query = 'doc LIKE ?'
        else:
            injection = (namelist, search_pattern)
            query = 'doc LIKE ? AND namelist=?'
        return [NamelistItem.from_tuple(item) for item in
                self.db.search_for_many('inlist_items', query, injection)]

    def doc(self, name):
        """Find documentation string for a namelist item

        Parameters
        ----------
        name : str
            Name of a valid inlist item

        Returns
        -------
        str
            Documentation for the namelist item"""
        return self.find_namelist_item(name).doc

    def default(self, name):
        """Find default value of a namelist item

        Parameters
        ----------
        name : str
            Name of a valid inlist item

        Returns
        -------
        TODO: FIGURE THIS OUT. Is a python primitive returned or a string?
        """
        return self.find_namelist_item(name).default

    def dtype(self, name):
        """Find data type (int, float, string, boolean) of a valid inlist item.

        Parameters
        ----------
        name : str
            Name of a valid inlist item

        Returns
        -------
        TODO: FIGURE THIS OUT. Is it a python function or a string?
        """
        return self.find_namelist_item(name).dtype

    def namelist(self, name):
        """Find and return the name of the inlist a valid inlist item belongs to

        Parameters
        ----------
        name : str
            Name of a valid inlist item

        Returns
        -------
        str :
            Name of the namelist that `name` belongs to.
        """
        return self.find_namelist_item(name).namelist

    def summary(self, name):
        """Create and return summary string about a valid namelist item

        Parameters
        ----------
        name : str
            Name of a valid inlist item

        Returns
        -------
        str:
            Multiline summary about the namelist item indicated by `name`
        """
        item = self.find_namelist_item(name)
        res = ("name:     {}\n".format(item.name) +
               "dtype:    {}\n".format(item.dtype) +
               "default:  {}\n".format(item.default) +
               "namelist: {}\n".format(item.namelist) +
               "doc:      \n\n{}".format(item.doc))
        return res

    @property
    def db(self):
        return self._db

    @property
    def data(self):
        if self._data is None:
            self._get_data()
        return self._data

    @property
    def names(self):
        if self._names is None:
            self._names = {namelist: [item['lower_name'] for item in
                                      self.data[namelist]]
                           for namelist in self.data.keys()}
        return self._names
