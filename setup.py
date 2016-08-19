"""
Warmachine setup.py file for distribution
"""
from setuptools import setup, find_packages

setup(
    name="dbolla",
    version='0.1',
    description="D'bolla is a no bullshit extensible IRC & Slack bot",
    packages=find_packages(),
    install_requires=['websockets', ],

    # See https://pypi.python.org/pypi?%3Aaction=list_classifiers
    classifiers=[
        'Development Status :: 3 - Alpha',

        'Intended Audience :: Developers',
        'Intended Audience :: System Administrators',

        'Topic :: Communications :: Chat',

        'License :: Other/Proprietary License',
        # 'License :: OSI Approved :: GNU Lesser General Public License v3 '
        # '(LGPLv3)',

        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',

    ],
    scripts=[
        'bin/dbolla',
    ],
)
