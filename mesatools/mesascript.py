import json
from os.path import join
import os
import string
import re

class NamelistItem(object):
    def __init__(self, name, dtype, dim, order, namelist, doc):
        self.name = name
        self.lower_name = string.lower(name)
        self.dtype = dtype
        self.shape = dim
        self.order = order
        self.namelist = namelist
        self.doc = doc

class BadPathError(Exception):
    def __init__(self, msg):
        Exception.__init__(self, msg)

def f_end(version):
    """Gives fortran file ending used in MESA depending on the version used

    Parameters
    ----------
    version : int
        version number of MESA to be checked

    Returns
    -------
    str
        Either 'f90' or 'f', depending on `version`.
    """
    if version >= 7380:
        return "f90"
    else:
        return "f"

def has_comment(line):
    return '!' in line

def is_comment(line):
    return bool(re.match('\A\s*!', line))

def is_blank(line):
    return bool(re.match('\A\s+\Z', line))

def full_line(lines, i):
    """Gives full line in one string

    Returns
    -------
    str
    """
    if lines[i][-1] != '&':
        return lines[i]
    else:
        return ' '.join([lines[i].replace('&', ''), full_line(lines, i+1)])

def full_doc_line(lines, i):
    if re.match("\A\s*!###", lines[i]):
        good_lines = [lines[i]]
        for line in lines[i+1]:
            if re.match('\A\s*!', line) or re.match('\A\s+\Z', line):
                good_lines.append(line)
            else:
                break
        return ''.join(good_lines)
    else:
        return None

def generate_language_file(mesa_dir=None, save_file=None):
    """Make JSON file that characterizes all valid inlist commands.

    Parameters
    ----------
    mesa_dir : str, optional
        path to mesa installation from which to generate language, default is
        taken from environment variable MESA_DIR
    save_loc : str, optional
        path to JSON file that should hold language information, default is
        `$MESA_DIR/data/mesascript_lang_XXXX.json` where the XXXX is the
        version number
    """

    # Try to find default mesa dir location if one isn't provided
    if mesa_dir is None:
        if 'MESA_DIR' not in os.environ:
            raise BadPathError('Could not find an environment variable ' +
                               'called MESA_DIR.')
        else:
            mesa_dir = os.environ['MESA_DIR']

    # Determine mesa version for use in determining file names
    with open(join(mesa_dir, 'data', 'version'), 'r') as f:
        version = int(f.readline())

    # Specify save location if one isn't provided
    if save_file is None:
        save_loc = join(mesa_dir, 'data', 'mesascript_lang_{:d}.json'.format(
                version))

    # Just do basic mesa star namelists now,
    # should be able to add support for binary, others easily, though
    # maybe through external configuration file that specifies namelist names
    # and asssociated definition and default files?
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
        'controls': [join(mesa_dir, 'star', 'private', 'star_controls.inc'),],
        'pgstar': [join(mesa_dir, 'star', 'private', 'pgstar_controls.inc')]
    }
    define_files['pgstar'].append(join(mesa_dir, 'star', 'private',
                                    'ctrls_io.{}'.format(f_end(version))))
    default_files = {namelist: join(mesa_dir, 'star', 'defaults', namelist +
                                    '.defaults') for namelist in namelists}
    # Each item has an associated converter function that will take inputs
    # and cast them to the appropriate data types.
    dtypes = {
        'logical': bool,
        'character': str,
        'integer': int,
        'real' : float,
        'type' : bool
    }

    # Bare-bones defaults for inlist items of each data type, should be
    # overwritten by reading from defaults files
    dfts = {
        bool: False,
        str: '',
        int: 0,
        float: 0.0
    }

    # Go through each namelist, pulling information with associated
    # definition and default files and buliding a dict of arrays of inlist
    # items.
    namelist_data = {}
    for namelist in namelists:
        namelist_data[namelist] = []
        for define_file in define_files[namelist]:
            try:
                with open(define_file, 'r') as f:
                    lines = f.readlines()
            except IOError as e:
                print "Couldn't open file {}.".format(define_file)
                next

            # Clean out lines that are entirely comments or blank
            cleaned_lines = []
            for line in lines:
                if not(is_comment(line) or is_blank(line)):
                    # Also remove inline comments
                    if '!' in line:
                        line = line[0:line.index('!')]
                    cleaned_lines.append(line.strip())

            # Now remove line-continuations, so each declaration is one
            # string without newlines, stopping for any defined subroutines
            # and functions.
            full_lines = []
            for i, line in enumerate(cleaned_lines):
                if re.match('\A\s*contains', line):
                    break
                if '::' not in line:
                    next
                else:
                    full_lines.append(full_line(cleaned_lines, i))

            # Break each full line into pairs of declaration information (
            # type, dimension, etc.) and names (one or more separated by
            # commas), ascertaining the type, dimension, and default value of
            # each variable.
            pairs = [[s.strip for s in line.split('::')] for line in full_lines]
            for this_type, names in pairs:
                if 'logical' in this_type:
                    dtype = dtypes['logical']
                elif 'character' in this_type:
                    dtype = dtypes['character']
                elif 'integer' in this_type:
                    dtype=dtypes['integer']
                elif 'real' in this_type:
                    dtype=dtypes['real']
                else:
                    dtype = None
                dft = dfts[dtype]
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
                        next
                    elif char == '(':
                        paren_level += 1
                    elif char == ')':
                        paren_level -= 1
                    new_names.append(char)
                new_names = (''.join(new_names).split(','))
                dimension_match = re.compile('dimension\((.*)\)', re.IGNORECASE)
                for name in new_names:
                    if re.match('\(.*\)', name):
                        num_indices = name.count('!') + 1
                        name = re.sub('\(.*\)', '')
                    elif dimension_match.match(this_type):
                        dim_match = dimension_match.match(this_type)
                        num_indices = dim_match.groups()[0].count(',') + 1
                    else:
                        num_indices = 0

                    # Add new record for namelist item, which will later be
                    # checked for more proper defaults, order,
                    # and documentation.
                    namelist_data[namelist].append(NamelistItem(name, dtype,
                                                                num_indices, -1,
                                                                namelist, ''))
        for default_file in default_files[namelist]:
            try:
                with open(default_file, 'r') as f:
                    lines = f.readlines()
            except IOError as e:
                print "Couldn't open file {}.".format(default_file)
                next

            for i, line in enumerate(lines):
                doc = full_doc_line(lines, i)
                if doc:
                    name = re.search('!###\s*(.*)\n', doc).groups()[0].strip()
                






