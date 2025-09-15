.. image:: https://img.shields.io/hexpm/l/plug.svg
    :target: http://www.apache.org/licenses/LICENSE-2.0

=============================
JIRA to TaskJuggler Convertor
=============================

Tool for converting a set of JIRA tasks to TaskJuggler (TJ3) syntax, with support for hierarchical task structures including Epics, Stories, and Sub-tasks.

----
Goal
----

When using JIRA to track your project, and tasks/issues are estimated using the time-tracking plugin, this python
module can convert the JIRA tasks to a gantt chart using the `TaskJuggler <http://taskjuggler.org/>`_ tool.

The tool supports both flat task lists and hierarchical task structures. With the hierarchical mode enabled,
Epics become parent tasks containing their child Stories and Sub-tasks, creating properly nested TaskJuggler
task structures with automatic effort rollup from children to parents.

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

**Basic Usage:**

.. code::

    jira-juggler -q "project = MYPROJECT" -o output.tjp

**Hierarchical Epic Support:**

To enable hierarchical task structures with Epics, Stories, and Sub-tasks, use the ``-E`` or ``--enable-epics`` flag:

.. code::

    jira-juggler -q "project = MYPROJECT" -E -o hierarchical_output.tjp

This will create nested TaskJuggler tasks where:

- Epics become parent tasks containing their child Stories
- Stories become parent tasks containing their child Sub-tasks
- Effort is automatically rolled up from children to parents
- Proper indentation is used for nested task structures

**Example Hierarchical Output:**

.. code::

    task EPIC_123 "User Management" {
        Jira "EPIC-123"
        allocate product_owner
        effort 5.0d

        task STORY_456 "User Authentication" {
            Jira "STORY-456"
            allocate backend_dev
            effort 3.0d

            task SUB_789 "Login API" {
                Jira "SUB-789"
                allocate backend_dev
                effort 1.0d
            }
        }
    }

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

.. note::

    **Epic and Hierarchy Detection**: The tool automatically detects hierarchical relationships through:

    - **Epic relationships**: Stories/Tasks linked to Epics via ``epic``, ``epiclink``, or custom fields like ``customfield_10014``
    - **Parent-child relationships**: Sub-tasks linked to their parent Stories/Tasks via the ``parent`` field
    - **Issue types**: Automatic detection of Epic and Sub-task issue types

    Only tasks included in your query results will be part of the hierarchy. Child tasks without their parents in
    the query results will appear as standalone top-level tasks.

--------------------
Command-line Options
--------------------

Key command-line options include:

- ``-q, --query``: **Required**. JQL query to fetch issues from JIRA
- ``-o, --output``: Output .tjp file (default: jira_export.tjp)
- ``-E, --enable-epics``: **NEW**. Enable hierarchical Epic/Story/Sub-task support
- ``-D, --depend-on-preceding``: Make tasks depend on preceding task with same assignee
- ``-s, --sort-on-sprint``: Sort tasks by sprint field (e.g., customfield_10851)
- ``-w, --weeklymax``: Workdays per week for time calculations (default: 5.0)
- ``-L, --links``: Specify issue link types for dependencies
- ``-l, --loglevel``: Logging level (default: warning)

Run ``jira-juggler -h`` for complete help.

**Comparison Example:**

Without ``-E`` (flat output):
::

    task EPIC_123 "User Management" { ... }
    task STORY_456 "User Authentication" { ... }
    task SUB_789 "Login API" { ... }

With ``-E`` (hierarchical output):
::

    task EPIC_123 "User Management" {
        task STORY_456 "User Authentication" {
            task SUB_789 "Login API" { ... }
        }
    }

-----------
Limitations
-----------

- When two tasks end on the same date and time, TaskJuggler won't necessarily preserve the order in which the tasks
  appear in jira-juggler's output.

- **Hierarchical mode**: Epic hierarchy is only enabled with the ``-E`` flag. By default, all tasks are output as a flat list
  to maintain backward compatibility.

- **Effort rollup**: When using hierarchical mode, parent task efforts are automatically calculated from their children.
  Manual effort estimates on parent tasks (Epics/Stories with children) may be overridden by the rollup calculation.
