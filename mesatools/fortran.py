import re


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
    full line of fortran code. This done by detecting if the line ends in an
    "&" and if it does, concatenating it with the next line (removing the &)
    and repeating the process recursively until a line does not end in an "&".

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
        return ' '.join([lines[i].replace('&', ''), full_line(lines, i + 1)])
