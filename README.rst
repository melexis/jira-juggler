.. image:: https://img.shields.io/hexpm/l/plug.svg
    :target: http://www.apache.org/licenses/LICENSE-2.0

=============================
JIRA to TaskJuggler convertor
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

Installation from pypi:

.. code::

    pip install mlx.jira_juggler

-----
Usage
-----

See help from python module:

.. code::

    jira-juggler -h

.. warning::

    The generated tj3-file, can at the moment not be parsed by TaskJuggler directly. Only the tasks are exported
    to the tj3-file. The list of tasks needs to be embedded in a complete tj3-file. See the
    `TaskJuggler website <http://taskjuggler.org/>`_ for more details.

