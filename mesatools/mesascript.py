import json
from os.path import join
import os
import string
import re

# Each item has an associated converter function that will take inputs
# and cast them to the appropriate data types.
dtype_funcs = {
    'bool': bool,
    'str': str,
    'int': int,
    'float' : float,
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
        self.lower_name = string.lower(name)
        self.dtype = dtype
        self.default = default
        self.dim = dim
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
    """Determines if a string contains a fortran comment."""
    return '!' in line

def is_comment(line):
    """Determines if a string is entirely a fortran comment."""
    return bool(re.match('\A\s*!', line))

def is_blank(line):
    """Determines if a string is entirely white space."""
    return bool(re.match('\A\s+\Z', line))

def full_line(lines, i):
    """Gives full line in one string

    Takes an array of strings, `lines`, and a starting index, `i` to obtain a
    full line of fortran code. This done by detecting if the line ends in an "&"
    and if it does, concatenating it with the next line (removing the &) and
    repeating the process recursively until a line does not end in an "&".

    Parameters
    ----------
    lines : array of strings
        array of lines from which to obtain a single line of fortran code
    i : int
        index of `lines` from which to start building the line

    Returns
    -------
    str
    """
    if lines[i][-1] != '&':
        return lines[i]
    else:
        return ' '.join([lines[i].replace('&', ''), full_line(lines, i+1)])

# TODO: Finish this up since multiple headers can share comment text
def full_doc_line(lines, i):
    if re.match("\A\s*!###", lines[i]):
        good_lines = [lines[i]]
        for line in lines[i+1:]:
            # include comments and blank lines only
            if re.match('\A\s*!', line) or re.match('\A\s+\Z', line):
                # but exclude other headers
                if re.match('\A\s*![^#]'):
                    good_lines.append(line)
            else:
                break
        return ''.join(good_lines)
    else:
        return None

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
    elif (('d' in val_string.lower()) or ('.' in val_string.lower()) or ('e'
          in val_string.lower())):
        dtype = 'float'
        val = val_string.lower().replace('d', 'e')
    elif re.match('\A-?\d+\Z', val_string.lower()):
        dtype = 'int'
        val = val_string
    else:
        print("Couldn't determine dtype of " +
              val_string +'. Keeping it as a string ' +
              'literal.')
        dtype = 'str'
        val = val_string
    val = dtype_funcs[dtype](val)
    return dtype, val



def get_mesa_dir(mesa_dir=None):
    # Try to find default mesa dir location if one isn't provided
    if mesa_dir is None:
        if 'MESA_DIR' not in os.environ:
            raise BadPathError('Could not find an environment variable ' +
                               'called MESA_DIR.')
        else:
            return os.environ['MESA_DIR']
    return mesa_dir


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

    # Confirm/find mesa directory
    mesa_dir = get_mesa_dir(mesa_dir)

    # Determine mesa version for use in determining file names
    with open(join(mesa_dir, 'data', 'version_number'), 'r') as f:
        version = int(f.readline())

    # Specify save location if one isn't provided
    if save_file is None:
        save_loc = join(mesa_dir, 'data', 'mesascript_lang_{:d}.json'.format(
                version))

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
        'controls': [join(mesa_dir, 'star', 'private', 'star_controls.inc'),],
        'pgstar': [join(mesa_dir, 'star', 'private', 'pgstar_controls.inc')]
    }
    define_files['pgstar'].append(join(mesa_dir, 'star', 'private',
                                    'ctrls_io.{}'.format(f_end(version))))
    default_files = {namelist: join(mesa_dir, 'star', 'defaults', namelist +
                                    '.defaults') for namelist in namelists}
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
                continue

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
                    continue
                else:
                    full_lines.append(full_line(cleaned_lines, i))

            # Break each full line into pairs of declaration information (
            # type, dimension, etc.) and names (one or more separated by
            # commas), ascertaining the type, dimension, and default value of
            # each variable.
            pairs = [[s.strip() for s in line.split('::')] for line in
                     full_lines]
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
                                                                dft,
                                                                num_indices, -1,
                                                                namelist, ''))
        default_file = default_files[namelist]
        # Read in lines from default files. If that fails, fail gracefully
        # and try opening the next one.
        try:
            with open(default_file, 'r') as f:
                lines = f.readlines()
        except IOError as e:
            print "Couldn't open file {}.".format(default_file)
            continue

        # Get all names for items in this namelist
        names = [item.name for item in namelist_data[namelist]]

        # Go through each line of the defaults file, looking for lines that
        # give markdown formatted documentation for a control. Then
        # extract name and documentation from comments, order, dtype and
        # default from its position and value in the file.
        order = 0
        for i, line in enumerate(lines):
            doc = full_doc_line(lines, i)
            if doc:
                # TODO: Update this to allow for multiple headers to share
                # doc lines
                name = re.search('!###\s*(.*)\n', doc).groups()[0].strip()
                if name not in names:
                    # print('Found item "{}" in defaults '.format(name) +
                    #       'file for namelist {}, but '.format(namelist) +
                    #       "didn't find it in definition file.")
                    continue
                # position in namelist_data[namelist] for item
                j = names.index(name)
                for k in range(i, len(lines)):
                    # find first line that ISN'T a comment or blank line
                    if re.match('\A\s*\!', lines[k]) or re.match('\A\s+\Z',
                                                           lines[k]):
                        # print("Skipping line " + lines[k])
                        continue
                    else:
                        # split definition line around equals sign
                        # print("Processing line " + lines[k])
                        def_line = lines[k].split('=')
                        # check if name of variable matches one in doc
                        assign_name = def_line[0].strip()
                        if assign_name.lower() != name.lower():
                            print("Warning: " + assign_name + " does not "+
                                  "match " + name + " in documentation.")
                        # get default value in string form
                        val_string = def_line[1].strip()
                        if '!' in val_string:
                            val_string = val_string[:val_string.index(
                                '!')].strip()
                        dtype, val = dtype_and_value(val_string)
                        break


                namelist_data[namelist][j].dtype = dtype
                namelist_data[namelist][j].default = val
                namelist_data[namelist][j].order = order
                namelist_data[namelist][j].doc = doc

                order += 1
    print(json.dumps(namelist_data))


if __name__ == '__main__':
    generate_language_file(mesa_dir=os.environ['MESA_DIR'],
                           save_file='/Users/wmwolf/Desktop/test.json')








