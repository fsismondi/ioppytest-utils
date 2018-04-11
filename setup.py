# Author:
#     Federico Sismondi <federico.sismondi@gmail.com>
#
# License: see LICENSE document

import io
from setuptools import setup, find_packages

MAJOR = 0
MINOR = 1
PATCH = 2
VERSION = "{}.{}.{}".format(MAJOR, MINOR, PATCH)

name = 'ioppytest-utils'
description = "Command line interface for interacting with ioppytest testing tool " \
              "(all interactions happen over AMQP even bus)."
CLASSIFIERS = [
    "Development Status :: 3 - Alpha",
    "Intended Audience :: Science/Research",
    "Intended Audience :: Developers",
    "Intended Audience :: Testers",
    "Intended Audience :: Network Testers",
    # "License :: OSI Approved :: BSD License",
    "Programming Language :: Python",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.5",
    "Programming Language :: Python :: 3.6",
    "Topic :: Networks",
    "Topic :: Interoperability testing",
    "Topic :: Scientific/Engineering",
    # "Operating System :: Microsoft :: Windows", not there yet..
    "Operating System :: POSIX",
    "Operating System :: Unix",
    "Operating System :: MacOS"
]

with open("version.py", "w") as f:
    f.write("__version__ = '{}'\n".format(VERSION))

setup(
    name=name,
    author='Federico Sismondi',
    author_email="federicosismondi@gmail.com",
    maintainer='Federico Sismondi',
    maintainer_email="federicosismondi@gmail.com",
    description=description,
    version=VERSION,
    license="??",
    classifiers=CLASSIFIERS,
    packages=find_packages(exclude=["tests"]),
    py_modules=['tabulate', 'event_bus_utils'],
    long_description=io.open('README.md', 'r', encoding='utf-8').read(),
    install_requires=[
        'click==6.7',
        'click_repl==0.1.2',
        'pika==0.11.0',
        'prompt_toolkit==1.0.15',
        'wcwidth==0.1.7',
    ],
    entry_points={'console_scripts': [
        'ioppytest-cli=ioppytest_cli.ioppytest_cli:main',
    ],
    },
)
