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
    """Determines if a string is entirely white space or empty."""
    return bool(re.match('\A\s*\Z', line))


def full_line(lines, i, return_count=False, count=1, continued=False):
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
    return_count : bool, optional
        whether or not to return total number of lines assumed into the
        returned full line. Useful for traversing an entire file rather than
        seeking just one full line
    count : int, optional
        number of lines assumed into full line so far. Should only be used
        internally for recursive calls. Default is 1
    continued : bool, optional
        whether or not the line currently being evaluated is the continuation
        of the previous line. Should only be used internally for recursive
        calls. Determines whether or not the strings will be stripped from
        left and right vs just the right side. Default is False

    Returns
    -------
    str
        A full line of valid (aside from length, potentially) Fortran code.
        Possibly blank or a comment

    Notes
    -----
    This assumes the last non-blank character in a continued line is an
    ampersand (&). It will FAIL if an inline comment comes after the ampersand.
    More precisely, it will interpret that line as a complete (and not
    continued) line in this case.
    """

    # There is not continuation character at the end, this is the line
    if len(lines[i].rstrip()) == 0 or lines[i].rstrip()[-1] != '&':
        res_line = ''
        if continued:
            res_line = lines[i].strip()
        else:
            res_line = lines[i].rstrip()

        if return_count:
            return res_line, count
        else:
            return count

    # There is a line continuation character. Look at subsequent lines and
    # concatenate over the continuation character
    else:
        next_line, count = full_line(lines, i + 1, return_count=True,
                                     count=count + 1, continued=True)
        this_line = re.sub('\s*&\s*', ' ', lines[i].rstrip())
        if return_count:
            return this_line + next_line, count
        else:
            return this_line + next_line


def full_lines(lines, include_blanks=True, include_comments=True):
    """Takes fortran code and returns a list of complete code lines

    The point is to get a list of lines of code that have no line continuation
    characters. Can take either a giant string with newlines or a list of
    strings with or without newlines. Returns a list of strings, each of which
    is a new complete line of fortran (possible blank, possibly a comment).

    Parameters
    ----------
    lines : str or list of str
        full string of codes with newlines or list of lines of code with or
        without newline characters
    include_blanks : boolean, optional
        whether or not to include blank lines. Defaults is True
    include_comments : boolean, optional
        whether or not to include lines that are only comments

    Returns
    -------
    list of str
        list of lines of code without newlines
    """

    # convert a giant string to a list of lines
    if type(lines) == str:
        lines = lines.split('\n')

    # build list of full lines from empty list
    res = []

    # iterate through lines and add full lines to result. After each line
    # is added move ahead a number of lines equal to the number used to
    # construct the line
    i = 0
    while i < len(lines):
        next_line, di = full_line(lines, i, return_count=True)
        res.append(next_line)
        i += di

    # If needed, toss blank lines and/or comments
    if not include_blanks:
        res = filter(lambda line: not is_blank(line), res)
    if not include_comments:
        res = filter(lambda line: not is_comment(line), res)

    return res
