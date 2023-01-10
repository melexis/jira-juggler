.. image:: https://img.shields.io/hexpm/l/plug.svg
    :target: http://www.apache.org/licenses/LICENSE-2.0

=============================
JIRA to TaskJuggler Convertor
=============================

Tool for converting a set of JIRA tasks to TaskJuggler (TJ3) syntax.

----
Goal
----

When using JIRA to track your project, and tasks/issues are estimated using the time-tracking plugin, this python
module can convert the JIRA tasks to a gantt chart using the `TaskJuggler <http://taskjuggler.org/>`_ tool.

------------
Installation
------------

Installation from PyPI:

.. code::

    pip install mlx.jira-juggler

-----
Usage
-----

See help from python module:

.. code::

    jira-juggler -h

By default, the following endpoint for the JIRA API is used: *https://melexis.atlassian.net*.
The script will ask you to input your email address (or username) and API token (or password). These three
variables can be configured by setting them in a *.env* file. This *.env* file shall be located in the directory where
pip has installed the package. You can find an example configuration in *.env.example*. JIRA Cloud requires the
combination of email address and API token, while JIRA Server might accept a username and password.

.. note::

    To include resolved **and** unresolved tasks while excluding invalid tasks, you can add the following logic to the
    value for the `--query` argument: `(resolution !=  Invalid OR resolution = Unresolved)`.

.. warning::

    The generated tj3-file, can at the moment not be parsed by TaskJuggler directly. Only the tasks are exported
    to the tj3-file. The list of tasks needs to be embedded in a complete tj3-file. See the
    `TaskJuggler website <http://taskjuggler.org/>`_ for more details.

.. note::

    Unresolved tasks with logged time, i.e. time spent, will have their 'start' property set to the set current date
    and time minus the logged time, calculated with 8 hours per workday and a default of 5 allocated workdays per week
    with the day(s) off ending on Sunday. The latter number can be changed.

-----------
Limitations
-----------

When two tasks end on the same date and time, TaskJuggler won't necessarily preserve the order in which the tasks
appear in jira-juggler's output.
