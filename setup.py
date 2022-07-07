from setuptools import find_packages, setup

PROJECT_URL = 'https://github.com/melexis/jira-juggler'

setup(
    name='mlx.jira_juggler',
    use_scm_version={
        'write_to': 'src/mlx/__version__.py'
    },
    url=PROJECT_URL,
    author='Stein Heselmans',
    author_email='teh@melexis.com',
    description='A python script for extracting data from Jira, and converting to task-juggler (tj3) output',
    long_description=open("README.rst").read(),
    long_description_content_type='text/x-rst',
    zip_safe=False,
    license='Apache License, Version 2.0',
    platforms='any',
    packages=find_packages('src'),
    package_dir={'': 'src'},
    entry_points={'console_scripts': ['jira-juggler = mlx.jira_juggler:entrypoint']},
    include_package_data=True,
    install_requires=['jira', 'python-dateutil>=2.8.0,<3.*', 'natsort>=7.1.0,<8.*', 'python-decouple'],
    setup_requires=['setuptools-scm>=6.0.0,<7.*'],
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
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
    ],
    keywords=[
        'Jira',
        'taskjuggler',
        'gantt',
        'project planning',
        'planning',
        'software engineering',
    ],
)
