from os import environ
from os.path import join


def get_mesa_dir(mesa_dir=None):
    # Try to find default mesa dir location if one isn't provided
    if mesa_dir is None:
        if 'MESA_DIR' not in environ:
            raise BadPathError('Could not find an environment variable ' +
                               'called MESA_DIR.')
        else:
            return environ['MESA_DIR']
    return mesa_dir

def mesa_dir():
    return environ['MESA_DIR']


def version():
    with open(join(mesa_dir(), 'data', 'version_number'), 'r') as f:
        ver_num = f.read().strip()
    return int(ver_num)
