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
setup file for leap.soledad
"""
import os
import re
import sys
import versioneer

from setuptools import setup
from setuptools import find_packages
from setuptools import Command
from setuptools.command.develop import develop as _cmd_develop

from pkg import utils


isset = lambda var: os.environ.get(var, None)
if isset('VIRTUAL_ENV') or isset('LEAP_SKIP_INIT'):
    data_files = None
else:
    # XXX this should go only for linux/mac
    data_files = [("/etc/init.d/", ["pkg/soledad-server"])]


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
    template = """
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


class cmd_develop(_cmd_develop):
    def run(self):
        # versioneer:
        versions = versioneer.get_versions(verbose=True)
        self._versioneer_generated_versions = versions
        # unless we update this, the command will keep using the old version
        self.distribution.metadata.version = versions["version"]
        _cmd_develop.run(self)


cmdclass = versioneer.get_cmdclass()
cmdclass["freeze_debianver"] = freeze_debianver
cmdclass["develop"] = cmd_develop


# XXX add ref to docs

install_requires = []
for reqfile in ["pkg/common/requirements.pip",
                "pkg/client/requirements.pip",
                "pkg/server/requirements.pip"]:
    install_requires += utils.parse_requirements([reqfile])

# needed until kali merges the py3 fork back into the main pysqlcipher repo
if sys.version_info.major >= 3:
    install_requires += ['pysqlcipher3']
else:
    install_requires += ['pysqlcipher']

if utils.is_develop_mode():
    print
    print("[WARNING] Skipping leap-specific dependencies "
          "because development mode is detected.")
    print("[WARNING] You can install "
          "the latest published versions with "
          "'pip install -r pkg/{common,client,server}/requirements-leap.pip'")
    print("[WARNING] Or you can instead do 'python setup.py develop' "
          "from the parent folder of each one of them.")
    print
else:
    reqfiles = [
        "pkg/common/requirements-leap.pip",
        "pkg/client/requirements-leap.pip",
        "pkg/server/requirements-leap.pip",
    ]
    install_requires += utils.parse_requirements(reqfiles=reqfiles)

setup(
    name='leap.soledad',
    version=versioneer.get_version(),
    cmdclass=cmdclass,
    url='https://leap.se/',
    download_url=DOWNLOAD_URL,
    license='GPLv3+',
    description='Synchronization of locally encrypted data among devices.',
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
    namespace_packages=["leap"],
    packages=find_packages('src', exclude=['*.tests', '*.tests.*']),
    package_dir={'': 'src'},
    package_data={'': ["*.sql"]},
    install_requires=install_requires,
    extras_require={'signaling': ['leap.common>=0.3.0']},
    data_files=data_files
)
