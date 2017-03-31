# -*- coding: utf-8 -*-
# setup.py
# Copyright (C) 2013 LEAP
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.
"""
setup file for leap.soledad.client
"""
import re
import sys
from setuptools import setup
from setuptools import find_packages
from setuptools import Command
import versioneer

trove_classifiers = (
    "Development Status :: 3 - Alpha",
    "Intended Audience :: Developers",
    "License :: OSI Approved :: "
    "GNU General Public License v3 or later (GPLv3+)",
    "Environment :: Console",
    "Operating System :: OS Independent",
    "Operating System :: POSIX",
    "Programming Language :: Python :: 2.6",
    "Programming Language :: Python :: 2.7",
    "Topic :: Database :: Front-Ends",
    "Topic :: Software Development :: Libraries :: Python Modules"
)

DOWNLOAD_BASE = ('https://github.com/leapcode/bitmask_client/'
                 'archive/%s.tar.gz')
_versions = versioneer.get_versions()
VERSION = _versions['version']
VERSION_REVISION = _versions['full-revisionid']
DOWNLOAD_URL = ""

# get the short version for the download url
_version_short = re.findall('\d+\.\d+\.\d+', VERSION)
if len(_version_short) > 0:
    VERSION_SHORT = _version_short[0]
    DOWNLOAD_URL = DOWNLOAD_BASE % VERSION_SHORT


class freeze_debianver(Command):

    """
    Freezes the version in a debian branch.
    To be used after merging the development branch onto the debian one.
    """
    user_options = []
    template = r"""
# This file was generated by the `freeze_debianver` command in setup.py
# Using 'versioneer.py' (0.16) from
# revision-control system data, or from the parent directory name of an
# unpacked source archive. Distribution tarballs contain a pre-generated copy
# of this file.

import json
import sys

version_json = '''
{
 "dirty": false,
 "error": null,
 "full-revisionid": "FULL_REVISIONID",
 "version": "VERSION_STRING"
}
'''  # END VERSION_JSON

def get_versions():
    return json.loads(version_json)
"""

    def initialize_options(self):
        pass

    def finalize_options(self):
        pass

    def run(self):
        proceed = str(raw_input(
            "This will overwrite the file _version.py. Continue? [y/N] "))
        if proceed != "y":
            print("He. You scared. Aborting.")
            return
        subst_template = self.template.replace(
            'VERSION_STRING', VERSION_SHORT).replace(
            'FULL_REVISIONID', VERSION_REVISION)
        versioneer_cfg = versioneer.get_config_from_root('.')
        with open(versioneer_cfg.versionfile_source, 'w') as f:
            f.write(subst_template)


cmdclass = versioneer.get_cmdclass()
cmdclass["freeze_debianver"] = freeze_debianver


# XXX add ref to docs

install_requires = [
    'twisted', 'scrypt', 'zope.proxy', 'cryptography',
    'leap.common', 'leap.soledad.common', 'treq']

# needed until kali merges the py3 fork back into the main pysqlcipher repo
if sys.version_info >= (3, 0):
    install_requires += ['pysqlcipher3']
else:
    install_requires += ['pysqlcipher']


setup(
    name='leap.soledad.client',
    version=VERSION,
    cmdclass=cmdclass,
    url='https://leap.se/',
    download_url=DOWNLOAD_URL,
    license='GPLv3+',
    description='Synchronization of locally encrypted data among devices '
                '(client components).',
    author='The LEAP Encryption Access Project',
    author_email='info@leap.se',
    maintainer='Kali Kaneko',
    maintainer_email='kali@leap.se',
    long_description=(
        "Soledad is the part of LEAP that allows application data to be "
        "securely shared among devices. It provides, to other parts of the "
        "LEAP project, an API for data storage and sync."
    ),
    classifiers=trove_classifiers,
    namespace_packages=["leap", "leap.soledad"],
    packages=find_packages('src'),
    package_dir={'': 'src'},
    install_requires=install_requires,
    extras_require={'signaling': ['leap.common>=0.3.0']},
)
