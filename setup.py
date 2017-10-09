import io
from glob import glob
from os.path import basename, dirname, join, splitext

from setuptools import find_packages, setup

PROJECT_URL = 'https://github.com/melexis/jira-juggler'
VERSION = '1.1.0'


def read(*names, **kwargs):
    return io.open(
        join(dirname(__file__), *names),
        encoding=kwargs.get('encoding', 'utf8')
    ).read()


setup(
    name='mlx.jira_juggler',
    version=VERSION,
    url=PROJECT_URL,
    download_url=PROJECT_URL + '/tarball/' + VERSION,
    author='Stein Heselmans',
    author_email='teh@melexis.com',
    description='A python script for extracting data from Jira, and converting to task-juggler (tj3) output',
    long_description=open("README.rst").read(),
    zip_safe=False,
    license='Apache License, Version 2.0',
    platforms='any',
    packages=find_packages('src'),
    package_dir={'': 'src'},
    py_modules=[splitext(basename(path))[0] for path in glob('src/*.py')],
    include_package_data=True,
    install_requires=['jira'],
    namespace_packages=['mlx'],
    classifiers=[
        # complete classifier list: http://pypi.python.org/pypi?%3Aaction=list_classifiers
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: Apache Software License',
        'Operating System :: Unix',
        'Operating System :: POSIX',
        'Operating System :: Microsoft :: Windows',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
    ],
    keywords = [
        'Jira',
        'taskjuggler',
        'gantt',
        'project planning',
        'planning',
        'software engineering',
    ],
)
