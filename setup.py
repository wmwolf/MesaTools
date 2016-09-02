from setuptools import setup

setup(name='mesatools',
    version='0.2.0',
    description='tools for interacting with MESA star and its output',
    author='William M. Wolf',
    author_email='wolfey6@gmail.com',
    license='MIT',
    packages=['mesatools'],
    entry_points={
        'console_scripts': [
            ('py_mesa = mesatools.cli:mesa')
        ]
    },
    install_requires=['numpy'],
    include_package_data=False,
    zip_safe=False)
