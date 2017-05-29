from setuptools import setup, find_packages

setup(
    name='swcc.jira_juggler',
    version='1.0.0',
    url='https://gitlab.melexis.com/swcc/scripts/',
    author='SWCC',
    author_email='teh@melexis.com',
    description='A python script for extracting data from Jira, and converting to task-juggler (tj3) output',
    zip_safe=False,
    classifiers=[
        # How mature is this project? Common values are
        #   3 - Alpha
        #   4 - Beta
        #   5 - Production/Stable
        'Development Status :: 4 - Beta',

        # Indicate who your project is intended for
        'Intended Audience :: Developers',
        'Topic :: Software Development :: Packaging',

        # Specify the Python versions you support here. In particular, ensure
        # that you indicate whether you support Python 2, Python 3 or both.
        'Programming Language :: Python :: 2'
        'Programming Language :: Python :: 3'
    ],
    platforms='any',
    packages=find_packages(),
    include_package_data=True,
    install_requires=['jira', 'logging'],
    namespace_packages=['swcc'],
    keywords = ['Jira', 'taskjuggler', 'gantt'],
)
