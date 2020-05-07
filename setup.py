#!/usr/bin/env python3

import os
from setuptools import setup, find_packages


here = os.path.abspath(os.path.dirname(__file__))
with open(os.path.join(here, 'README.md')) as f:
    README = f.read()

if __name__ == "__main__":
    setup(
        name = 'rackit',
        setup_requires = ['setuptools_scm'],
        use_scm_version = True,
        description = 'Toolkit for building REST API clients.',
        long_description = README,
        classifiers = [
            "Programming Language :: Python",
            "Topic :: Internet :: WWW/HTTP",
        ],
        author = 'Matt Pryor',
        author_email = 'matt.pryor@stfc.ac.uk',
        url = 'https://github.com/cedadev/rackit',
        keywords = 'rest api http client toolkit toolbox',
        packages = find_packages(),
        include_package_data = True,
        zip_safe = False,
        install_requires = ['requests'],
    )
