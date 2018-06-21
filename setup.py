# Author:
#     Federico Sismondi <federicosismondi@gmail.com>

import io
from setuptools import setup, find_packages

MAJOR = 1
MINOR = 2
PATCH = 1
VERSION = "{}.{}.{}".format(MAJOR, MINOR, PATCH)

name = 'ioppytest-utils'
description = "Set of useful packages, modules  and programs for ioppytest components." \
              "Installs `ioppytest-cli` Command line interface for interacting with ioppytest testing tool " \
              "(all interactions happen over AMQP event bus)."
CLASSIFIERS = [
    "Development Status :: 3 - Alpha",
    "Intended Audience :: Science/Research",
    "Intended Audience :: Developers",
    "Programming Language :: Python",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.5",
    "Programming Language :: Python :: 3.6",
    "Topic :: Internet",
    "Topic :: Software Development :: Testing",
    "Topic :: Scientific/Engineering",
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
    url='https://gitlab.f-interop.eu/f-interop-contributors/utils',
    description=description,
    version=VERSION,
    license='GPLv3+',
    classifiers=CLASSIFIERS,
    packages=['event_bus_utils'],
    py_modules=['tabulate', 'messages', 'pure_pcapy'],
    long_description=io.open('README.md', 'r', encoding='utf-8').read(),
    long_description_content_type='text/markdown',
    install_requires=[
        'click==6.7',
        'click_repl==0.1.2',
        'pika==0.11.0',
        'prompt_toolkit==1.0.15',
        'wcwidth==0.1.7',
    ],
    entry_points={'console_scripts': ['ioppytest-cli=ioppytest_cli.ioppytest_cli:main']},
)
