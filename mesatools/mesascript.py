import json
from os.path import join
import os
import string
import re

class NamelistItem(object):
    def __init__(self, name, dtype, shape, order, namelist, doc):
        self.name = name
        self.lower_name = string.lower(name)
        self.dtype = dtype
        self.shape = shape
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


def generate_language_file(mesa_dir=None, save_loc=None):
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
    if mesa_dir is None:
        if 'MESA_DIR' not in os.environ:
            raise BadPathError('Could not find an environment variable ' +
                               'called MESA_DIR.')
        else:
            mesa_dir = os.environ['MESA_DIR']
    with open(join(mesa_dir, 'data', 'version'), 'r') as f:
        version = int(f.readline())
    if save_loc is None:
        save_loc = join(mesa_dir, 'data', 'mesascript_lang_{:d}.json'.format(
                version))
    namelists = ['star_job', 'controls', 'pgstar']
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
    dtypes = {
        'logical': bool,
        'character': str,
        'integer': int,
        'real' : float,
        'type' : bool
    }
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
            cleaned_lines = []
            for line in lines:
                if not(is_comment(line) or is_blank(line)):
                    cleaned_lines.append(line.strip())
            full_lines = []
            for i, line in enumerate(cleaned_lines):
                if re.match('\A\s*contains', line):
                    break
                if '::' not in line:
                    next
                else:
                    full_lines.append(full_line(cleaned_lines, i))
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
                name_chars = list(names)
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



