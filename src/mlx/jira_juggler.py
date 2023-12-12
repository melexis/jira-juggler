#! /usr/bin/python3
"""
Jira to task-juggler extraction script

This script queries Jira, and generates a task-juggler input file to generate a Gantt chart.
"""
import argparse
import logging
import re
from abc import ABC
from datetime import datetime, time
from functools import cmp_to_key
from getpass import getpass
from itertools import chain
from operator import attrgetter

from dateutil import parser
from decouple import config
from jira import JIRA, JIRAError
from natsort import natsorted, ns

DEFAULT_LOGLEVEL = 'warning'
DEFAULT_JIRA_URL = 'https://melexis.atlassian.net'
DEFAULT_OUTPUT = 'jira_export.tjp'

JIRA_PAGE_SIZE = 50

TAB = ' ' * 4


def fetch_credentials():
    """ Fetches the credentials from the .env file by default or, alternatively, from the user's input

    Returns:
        str: email address or username
        str: API token or password
    """
    username = config('JIRA_USERNAME', default='')
    api_token = config('JIRA_API_TOKEN', default='')
    if not username:
        username = input('JIRA email address (or username): ')
    if not api_token:
        password = config('JIRA_PASSWORD', default='')
        if password:
            logging.warning('Basic authentication with a JIRA password may be deprecated. '
                            'Consider defining an API token as environment variable JIRA_API_TOKEN instead.')
            return username, password
        else:
            api_token = getpass(f'JIRA API token (or password) for {username}: ')
    return username, api_token


def set_logging_level(loglevel):
    """Sets the logging level

    Args:
        loglevel (str): String representation of the loglevel
    """
    numeric_level = getattr(logging, loglevel.upper(), None)
    if not isinstance(numeric_level, int):
        raise ValueError('Invalid log level: %s' % loglevel)
    logging.basicConfig(level=numeric_level)


def to_identifier(key):
    """Converts given key to identifier, interpretable by TaskJuggler as a task-identifier

    Args:
        key (str): Key to be converted

    Returns:
        str: Valid task-identifier based on given key
    """
    return key.replace('-', '_')


def to_juggler_date(date):
    """Converts given datetime object to a string that can be interpreted by TaskJuggler

    The resolution is 60 minutes.

    Args:
        date (datetime.datetime): Datetime object

    Returns:
        str: String representing the date and time in TaskJuggler's format
    """
    return date.strftime('%Y-%m-%d-%H:00-%z').rstrip('-')


def calculate_weekends(date, workdays_passed, weeklymax):
    """Calculates the number of weekends between the given date and the amount of workdays to travel back in time.

    The following assumptions are made: each workday starts at 9 a.m., has no break and is 8 hours long.

    Args:
        date (datetime.datetime): Date and time specification to use as a starting point
        workdays_passed (float): Number of workdays passed since the given date
        weeklymax (float): Number of allocated workdays per week

    Returns:
        int: The number of weekends between the given date and the amount of weekdays that have passed since then
    """
    weekend_count = 0
    workday_percentage = (date - datetime.combine(date.date(), time(hour=9))).seconds / JugglerTaskEffort.FACTOR
    date_as_weekday = date.weekday() + workday_percentage
    if date_as_weekday > weeklymax:
        date_as_weekday = weeklymax
    remaining_workdays_passed = workdays_passed - date_as_weekday
    if remaining_workdays_passed > 0:
        weekend_count += 1 + (remaining_workdays_passed // weeklymax)
    return weekend_count


def to_username(value):
    """Converts the given value to a username (user ID), if needed, while caching the result.

    Args:
        value (str/jira.User): String (account ID or user ID) or User instance

    Returns:
        str: The corresponding username
    """
    user_id = value.accountId if hasattr(value, 'accountId') else str(value)
    if user_id in id_to_username_mapping:
        return id_to_username_mapping[user_id]

    if not isinstance(value, str):
        id_to_username_mapping[user_id] = determine_username(value)
    elif len(value) >= 24:  # accountId
        user = jirahandle.user(user_id)
        id_to_username_mapping[user_id] = determine_username(user)
    return id_to_username_mapping.get(user_id, value)


def determine_username(user):
    """Determines the username (user ID) for the given User.

    Args:
        user (jira.User): User instance

    Returns
        str: Corresponding username

    Raises:
        Exception: Failed to determine username
    """
    if getattr(user, 'emailAddress', ''):
        username = user.emailAddress.split('@')[0]
    elif getattr(user, 'name', ''):  # compatibility with Jira Server
        username = user.name
    elif getattr(user, 'displayName', ''):
        full_name = user.displayName
        username = f'"{full_name}"'
        logging.error(f"Failed to fetch email address of {full_name!r}: they restricted its visibility; "
                      f"using identifier {username!r} as fallback value.")
    else:
        raise Exception(f"Failed to determine username of {user}")
    return username


def determine_default_links(link_types_per_name):
    default_links = []
    for link_types in ({'Blocker': 'inward', 'Blocks': 'inward'}, {'Dependency': 'outward', 'Dependent': 'outward'}):
        for link_type_name, direction in link_types.items():
            if link_type_name in link_types_per_name:
                link = getattr(link_types_per_name[link_type_name], direction)
                default_links.append(link)
                break
        else:
            logging.warning("Failed to find any of these default jira-juggler issue link types in your Jira project "
                            f"configuration: {list(link_types)}. Use --links if you think this is a problem.")
    return default_links


def determine_links(jira_link_types, input_links):
    valid_links = set()
    if input_links is None:
        link_types_per_name = {link_type.name: link_type for link_type in jira_link_types}
        valid_links = determine_default_links(link_types_per_name)
    elif input_links:
        unique_input_links = set(input_links)
        all_jira_links = chain.from_iterable((link_type.inward, link_type.outward) for link_type in jira_link_types)
        missing_links = unique_input_links.difference(all_jira_links)
        if missing_links:
            logging.warning(f"Failed to find links {missing_links} in your configuration in Jira")
        valid_links = unique_input_links - missing_links
    return valid_links


class JugglerTaskProperty(ABC):
    """Class for a property of a Task Juggler"""

    DEFAULT_NAME = 'property name'
    DEFAULT_VALUE = 'not initialized'
    PREFIX = ''
    SUFFIX = ''
    TEMPLATE = TAB + '{prop} {value}\n'
    VALUE_TEMPLATE = '{prefix}{value}{suffix}'

    def __init__(self, jira_issue=None):
        """Initializes the task juggler property

        Args:
            jira_issue (jira.resources.Issue): The Jira issue to load from
            value (object): Value of the property
        """
        self.name = self.DEFAULT_NAME
        self.value = self.DEFAULT_VALUE

        if jira_issue:
            self.load_from_jira_issue(jira_issue)

    @property
    def is_empty(self):
        """bool: True if the property contains an empty or uninitialized value"""
        return not self.value or self.value == self.DEFAULT_VALUE

    def clear(self):
        """Sets the name and value to the default"""
        self.name = self.DEFAULT_NAME
        self.value = self.DEFAULT_VALUE

    def load_from_jira_issue(self, jira_issue):
        """Loads the object with data from a Jira issue

        Args:
            jira_issue (jira.resources.Issue): The Jira issue to load from
        """

    def validate(self, task, tasks):
        """Validates (and corrects) the current task property

        Args:
            task (JugglerTask): Task to which the property belongs
            tasks (list): List of JugglerTask instances to which the current task belongs. Will be used to
                verify relations to other tasks.
        """

    def __str__(self):
        """Converts task property object to the task juggler syntax

        Returns:
            str: String representation of the task property in juggler syntax
        """
        if self.value is not None:
            return self.TEMPLATE.format(prop=self.name,
                                        value=self.VALUE_TEMPLATE.format(prefix=self.PREFIX,
                                                                         value=self.value,
                                                                         suffix=self.SUFFIX))
        return ''


class JugglerTaskAllocate(JugglerTaskProperty):
    """Class for the allocation (assignee) of a juggler task"""

    DEFAULT_NAME = 'allocate'
    DEFAULT_VALUE = '"not assigned"'

    def load_from_jira_issue(self, jira_issue):
        """Loads the object with data from a Jira issue.

        The last assignee in the Analyzed state of the Jira issue is prioritized over the current assignee,
        which is the fallback value.

        Args:
            jira_issue (jira.resources.Issue): The Jira issue to load from
        """
        if jira_issue.fields.status.name in ('Closed', 'Resolved'):
            before_resolved = False
            for change in sorted(jira_issue.changelog.histories, key=attrgetter('created'), reverse=True):
                for item in change.items:
                    if item.field.lower() == 'assignee':
                        if not before_resolved:
                            self.value = getattr(item, 'from', None)
                            if self.value:
                                self.value = to_username(self.value)
                        else:
                            self.value = to_username(item.to)
                            return  # got last assignee before transition to Approved/Resolved status
                    elif item.field.lower() == 'status' and item.toString.lower() in ('approved', 'resolved'):
                        before_resolved = True
                        if self.value and self.value != self.DEFAULT_VALUE:
                            return  # assignee was changed after transition to Closed/Resolved status

        if self.is_empty:
            if getattr(jira_issue.fields, 'assignee', None):
                self.value = to_username(jira_issue.fields.assignee)
            else:
                self.value = self.DEFAULT_VALUE


class JugglerTaskEffort(JugglerTaskProperty):
    """Class for the effort (estimate) of a juggler task"""

    # For converting the seconds (Jira) to days
    UNIT = 'd'
    FACTOR = 8.0 * 60 * 60

    DEFAULT_NAME = 'effort'
    MINIMAL_VALUE = 1.0 / 8
    DEFAULT_VALUE = MINIMAL_VALUE
    SUFFIX = UNIT

    def load_from_jira_issue(self, jira_issue):
        """Loads the object with data from a Jira issue

        Args:
            jira_issue (jira.resources.Issue): The Jira issue to load from
        """
        if hasattr(jira_issue.fields, 'timeoriginalestimate'):
            estimated_time = jira_issue.fields.timeoriginalestimate
            if estimated_time is not None:
                self.value = estimated_time / self.FACTOR
                logged_time = jira_issue.fields.timespent if jira_issue.fields.timespent else 0
                if jira_issue.fields.status.name in ('Closed', 'Resolved'):
                    # resolved ticket: prioritize Logged time over Estimated
                    if logged_time:
                        self.value = logged_time / self.FACTOR
                elif jira_issue.fields.timeestimate is not None:
                    # open ticket prioritize Remaining time over Estimated
                    if jira_issue.fields.timeestimate:
                        self.value = jira_issue.fields.timeestimate / self.FACTOR
                    else:
                        self.value = self.MINIMAL_VALUE
            else:
                self.value = 0
        else:
            self.value = self.DEFAULT_VALUE
            logging.warning('No estimate found for %s, assuming %s%s', jira_issue.key, self.DEFAULT_VALUE, self.UNIT)

    def validate(self, task, tasks):
        """Validates (and corrects) the current task property

        Args:
            task (JugglerTask): Task to which the property belongs
            tasks (list): Modifiable list of JugglerTask instances to which the current task belongs. Will be used to
                verify relations to other tasks.
        """
        if self.value == 0:
            logging.warning('Estimate for %s, is 0. Excluding', task.key)
            tasks.remove(task)
        elif self.value < self.MINIMAL_VALUE:
            logging.warning('Estimate %s%s too low for %s, assuming %s%s', self.value, self.UNIT, task.key, self.MINIMAL_VALUE, self.UNIT)
            self.value = self.MINIMAL_VALUE


class JugglerTaskDepends(JugglerTaskProperty):
    """Class for linking of a juggler task"""

    DEFAULT_NAME = 'depends'
    DEFAULT_VALUE = []
    PREFIX = '!'
    links = set()

    def append_value(self, value):
        """Appends value for task juggler property

        Args:
            value (object): Value to append to the property
        """
        if value not in self.value:
            self.value.append(value)

    def load_from_jira_issue(self, jira_issue):
        """Loads the object with data from a Jira issue

        Args:
            jira_issue (jira.resources.Issue): The Jira issue to load from
        """
        self.value = list(self.DEFAULT_VALUE)
        if hasattr(jira_issue.fields, 'issuelinks'):
            for link in jira_issue.fields.issuelinks:
                if hasattr(link, 'inwardIssue') and link.type.inward in self.links:
                    self.append_value(to_identifier(link.inwardIssue.key))
                elif hasattr(link, 'outwardIssue') and link.type.outward in self.links:
                    self.append_value(to_identifier(link.outwardIssue.key))

    def validate(self, task, tasks):
        """Validates (and corrects) the current task property

        Args:
            task (JugglerTask): Task to which the property belongs
            tasks (list): List of JugglerTask instances to which the current task belongs. Will be used to
                verify relations to other tasks.
        """
        task_ids = [to_identifier(tsk.key) for tsk in tasks]
        for val in list(self.value):
            if val not in task_ids:
                logging.warning('Removing link to %s for %s, as not within scope', val, task.key)
                self.value.remove(val)

    def __str__(self):
        """Converts task property object to the task juggler syntax

        Returns:
            str: String representation of the task property in juggler syntax
        """
        if self.value:
            valstr = ''
            for val in self.value:
                if valstr:
                    valstr += ', '
                valstr += self.VALUE_TEMPLATE.format(prefix=self.PREFIX,
                                                     value=val,
                                                     suffix=self.SUFFIX)
            return self.TEMPLATE.format(prop=self.name,
                                        value=valstr)
        return ''


class JugglerTaskTime(JugglerTaskProperty):
    """Class for setting the start/end time of a juggler task"""

    DEFAULT_VALUE = ''
    PREFIX = ''

    def validate(self, *_):
        """Validates the current task property"""
        if not self.is_empty:
            valid_names = ('start', 'end')
            if self.name not in valid_names:
                raise ValueError(f'The name of {self.__class__.__name__} is invalid; expected a value in {valid_names}')

    def __str__(self):
        """Converts task property object to the task juggler syntax

        Returns:
            str: String representation of the task property in juggler syntax
        """
        if self.value:
            return self.TEMPLATE.format(prop=self.name,
                                        value=self.value)
        return ''


class JugglerTask:
    """Class for a task for Task-Juggler"""

    DEFAULT_KEY = 'NOT_INITIALIZED'
    MAX_SUMMARY_LENGTH = 70
    DEFAULT_SUMMARY = 'Task is not initialized'
    TEMPLATE = '''
task {id} "{description}" {{
{tab}Jira "{key}"
{props}
}}
'''

    def __init__(self, jira_issue=None):
        logging.info('Create JugglerTask for %s', jira_issue.key)

        self.key = self.DEFAULT_KEY
        self.summary = self.DEFAULT_SUMMARY
        self.properties = {}
        self.issue = None
        self._resolved_at_date = None

        if jira_issue:
            self.load_from_jira_issue(jira_issue)

    def load_from_jira_issue(self, jira_issue):
        """Loads the object with data from a Jira issue

        Args:
            jira_issue (jira.resources.Issue): The Jira issue to load from
        """
        self.key = jira_issue.key
        self.issue = jira_issue
        summary = jira_issue.fields.summary.replace('\"', '\\\"')
        self.summary = (summary[:self.MAX_SUMMARY_LENGTH] + '...') if len(summary) > self.MAX_SUMMARY_LENGTH else summary
        if self.is_resolved:
            self.resolved_at_date = self.determine_resolved_at_date()
        self.properties['allocate'] = JugglerTaskAllocate(jira_issue)
        self.properties['effort'] = JugglerTaskEffort(jira_issue)
        self.properties['depends'] = JugglerTaskDepends(jira_issue)
        self.properties['time'] = JugglerTaskTime()

    def validate(self, tasks, property_identifier):
        """Validates (and corrects) the current task

        Args:
            tasks (list): List of JugglerTask instances to which the current task belongs. Will be used to
                verify relations to other tasks.
            property_identifier (str): Identifier of property type
        """
        if self.key == self.DEFAULT_KEY:
            logging.error('Found a task which is not initialized')
        self.properties[property_identifier].validate(self, tasks)

    def __str__(self):
        """Converts the JugglerTask to the task juggler syntax

        Returns:
            str: String representation of the task in juggler syntax
        """
        props = "".join(map(str, self.properties.values()))
        return self.TEMPLATE.format(id=to_identifier(self.key),
                                    key=self.key,
                                    tab=TAB,
                                    description=self.summary.replace('\"', '\\\"'),
                                    props=props)

    @property
    def is_resolved(self):
        """bool: True if JIRA issue has been approved/resolved/closed; False otherwise"""
        return self.issue is not None and self.issue.fields.status.name in ('Approved', 'Resolved', 'Closed')

    @property
    def resolved_at_repr(self):
        """str: Representation of date and time with resolution of 1 hour corresponding to the last transition to the
            Resolved status, ignoring timezone info; empty when not resolved
        """
        date = self.resolved_at_date
        if date:
            return to_juggler_date(date)
        return ""

    @property
    def resolved_at_date(self):
        """datetime.datetime: Date and time corresponding to the last transition to the Approved/Resolved status; the
            transition to the Closed status is used as fallback; None when not resolved
        """
        return self._resolved_at_date

    @resolved_at_date.setter
    def resolved_at_date(self, value):
        self._resolved_at_date = value

    def determine_resolved_at_date(self):
        closed_at_date = None
        for change in sorted(self.issue.changelog.histories, key=attrgetter('created'), reverse=True):
            for item in change.items:
                if item.field.lower() == 'status':
                    status = item.toString.lower()
                    if status in ('approved', 'resolved'):
                        return parser.isoparse(change.created)
                    elif status in ('closed',) and closed_at_date is None:
                        closed_at_date = parser.isoparse(change.created)
        return closed_at_date


class JiraJuggler:
    """Class for task-juggling Jira results"""

    def __init__(self, endpoint, user, token, query, links=None):
        """Constructs a JIRA juggler object

        Args:
            endpoint (str): Endpoint for the Jira Cloud (or Server)
            user (str): Email address (or username)
            token (str): API token (or password)
            query (str): The query to run
            links (set/None): List of issue link type inward/outward links; None to use the default configuration
        """
        global id_to_username_mapping
        id_to_username_mapping = {}
        logging.info('Jira endpoint: %s', endpoint)

        global jirahandle
        jirahandle = JIRA(endpoint, basic_auth=(user, token))
        logging.info('Query: %s', query)
        self.query = query
        self.issue_count = 0

        all_jira_link_types = jirahandle.issue_link_types()
        JugglerTaskDepends.links = determine_links(all_jira_link_types, links)

    @staticmethod
    def validate_tasks(tasks):
        """Validates (and corrects) tasks

        Args:
            tasks (list): List of JugglerTask instances to validate
        """
        for property_identifier in ('allocate', 'effort', 'depends', 'time'):
            for task in list(tasks):
                task.validate(tasks, property_identifier)

    def load_issues_from_jira(self, depend_on_preceding=False, sprint_field_name='', **kwargs):
        """Loads issues from Jira

        Args:
            depend_on_preceding (bool): True to let each task depend on the preceding task that has the same user
                allocated to it, unless it is already linked; False to not add these links
            sprint_field_name (str): Name of field to sort tasks on

        Returns:
            list: A list of JugglerTask instances
        """
        tasks = []
        busy = True
        while busy:
            try:
                issues = jirahandle.search_issues(self.query, maxResults=JIRA_PAGE_SIZE, startAt=self.issue_count,
                                                  expand='changelog')
            except JIRAError:
                logging.error('Invalid Jira query "%s"', self.query)
                return None

            if len(issues) <= 0:
                busy = False

            self.issue_count += len(issues)
            for issue in issues:
                logging.debug('Retrieved %s: %s', issue.key, issue.fields.summary)
                tasks.append(JugglerTask(issue))

        self.validate_tasks(tasks)
        if sprint_field_name:
            self.sort_tasks_on_sprint(tasks, sprint_field_name)
        tasks.sort(key=cmp_to_key(self.compare_status))
        if depend_on_preceding:
            self.link_to_preceding_task(tasks, **kwargs)
        return tasks

    def juggle(self, output=None, **kwargs):
        """Queries JIRA and generates task-juggler output from given issues

        Args:
            list: A list of JugglerTask instances
        """
        juggler_tasks = self.load_issues_from_jira(**kwargs)
        if not juggler_tasks:
            return None
        if output:
            with open(output, 'w', encoding='utf-8') as out:
                for task in juggler_tasks:
                    out.write(str(task))
        return juggler_tasks

    @staticmethod
    def link_to_preceding_task(tasks, weeklymax=5.0, current_date=datetime.now()):
        """Links task to preceding task with the same assignee.

        If the task has been resolved, 'end' is added instead of 'depends' no matter what, followed by the
        date and time on which it's been resolved.

        If it's the first unresolved task for a given assignee, 'start' is added followed by the date and hour on which
        the task has been started, i.e. current time minus time spent.
        For the other unresolved tasks, the effort estimate is 'Remaining' time
        only instead of 'Remaining + Logged' time since parallellism is not supported by
        TaskJuggler and this approach results in a more accurate forecast.

        Args:
            tasks (list): List of JugglerTask instances to modify
            weeklymax (float): Number of allocated workdays per week
            current_date (datetime.datetime): Offset-naive datetime to treat as the current date
        """
        id_to_task_map = {to_identifier(task.key): task for task in tasks}
        current_date_str = to_juggler_date(current_date)
        unresolved_tasks = {}
        for task in tasks:
            assignee = str(task.properties['allocate'])

            depends_property = task.properties['depends']
            time_property = task.properties['time']

            if task.is_resolved:
                depends_property.clear()  # don't output any links from JIRA
                time_property.name = 'end'
                time_property.value = task.resolved_at_repr
            else:
                if assignee in unresolved_tasks:  # link to a preceding unresolved task
                    preceding_task = unresolved_tasks[assignee][-1]
                    depends_property.append_value(to_identifier(preceding_task.key))
                else:  # first unresolved task for assignee: set start time unless it depends on an unresolved task
                    for identifier in depends_property.value:
                        if not id_to_task_map[identifier].is_resolved:
                            break
                    else:
                        start_time = current_date_str
                        if task.issue.fields.timespent:
                            effort_property = task.properties['effort']
                            effort_property.value += task.issue.fields.timespent / JugglerTaskEffort.FACTOR
                            days_spent = task.issue.fields.timespent // 3600 / 8
                            weekends = calculate_weekends(current_date, days_spent, weeklymax)
                            days_per_weekend = min(2, 7 - weeklymax)
                            start_time = f"%{{{start_time} - {days_spent + weekends * days_per_weekend}d}}"
                        time_property.name = 'start'
                        time_property.value = start_time

                unresolved_tasks.setdefault(assignee, []).append(task)

    def sort_tasks_on_sprint(self, tasks, sprint_field_name):
        """Sorts given list of tasks based on the values of the field with the given name.

        JIRA issues that are not assigned to a sprint will be ordered last.

        Args:
            tasks (list): List of JugglerTask instances to sort in place
            sprint_field_name (str): Name of the field that contains information about sprints
        """
        priorities = {
            "ACTIVE": 3,
            "FUTURE": 2,
            "CLOSED": 1,
        }
        for task in tasks:
            task.sprint_name = ""
            task.sprint_priority = 0
            task.sprint_start_date = None
            if not task.issue:
                continue
            values = getattr(task.issue.fields, sprint_field_name, None)
            if values is not None:
                if isinstance(values, str):
                    values = [values]
                for sprint_info in values:
                    state = ""
                    if isinstance(sprint_info, (str, bytes)):  # Jira Server
                        state_match = re.search("state=({})".format("|".join(priorities)), sprint_info)
                        if state_match:
                            state = state_match.group(1)
                            prio = priorities[state]
                            if prio > task.sprint_priority:
                                task.sprint_name = re.search("name=(.+?),", sprint_info).group(1)
                                task.sprint_priority = prio
                                task.sprint_start_date = self.extract_start_date(sprint_info, task.issue.key)
                    else:  # Jira Cloud
                        state = sprint_info.state.upper()
                        if state in priorities:
                            prio = priorities[state]
                            if prio > task.sprint_priority:
                                task.sprint_name = sprint_info.name
                                task.sprint_priority = prio
                                if hasattr(sprint_info, 'startDate'):
                                    task.sprint_start_date = parser.parse(sprint_info.startDate)
        logging.debug("Sorting tasks based on sprint information...")
        tasks.sort(key=cmp_to_key(self.compare_sprint_priority))

    @staticmethod
    def extract_start_date(sprint_info, issue_key):
        """Extracts the start date from the given info string.

        Args:
            sprint_info (str): Raw information about a sprint, as returned by the JIRA API
            issue_key (str): Name of the JIRA issue

        Returns:
            datetime.datetime/None: Start date as a datetime object or None if the sprint does not have a start date
        """
        start_date_match = re.search("startDate=(.+?),", sprint_info)
        if start_date_match:
            start_date_str = start_date_match.group(1)
            if start_date_str != '<null>':
                try:
                    return parser.parse(start_date_match.group(1))
                except parser.ParserError as err:
                    logging.debug("Failed to parse start date of sprint of issue %s: %s", issue_key, err)
                    return None

    @staticmethod
    def compare_sprint_priority(a, b):
        """Compares the priority of two tasks based on the sprint information

        The sprint_priority attribute is taken into account first, followed by the sprint_start_date and, lastly, the
        sprint_name attribute using natural sorting (a sprint with the word 'backlog' in its name is sorted as last).

        Args:
            a (JugglerTask): First JugglerTask instance in the comparison
            b (JugglerTask): Second JugglerTask instance in the comparison

        Returns:
            int: 0 for equal priority; -1 to prioritize a over b; 1 otherwise
        """
        if a.sprint_priority > b.sprint_priority:
            return -1
        if a.sprint_priority < b.sprint_priority:
            return 1
        if a.sprint_priority == 0 or a.sprint_name == b.sprint_name:
            return 0  # no/same sprint associated with both issues
        if type(a.sprint_start_date) != type(b.sprint_start_date):  # noqa
            return -1 if b.sprint_start_date is None else 1
        if a.sprint_start_date == b.sprint_start_date:
            # a sprint with backlog in its name has lower priority
            if "backlog" not in a.sprint_name.lower() and "backlog" in b.sprint_name.lower():
                return -1
            if "backlog" in a.sprint_name.lower() and "backlog" not in b.sprint_name.lower():
                return 1
            if natsorted([a.sprint_name, b.sprint_name], alg=ns.IGNORECASE)[0] == a.sprint_name:
                return -1
            return 1
        if a.sprint_start_date < b.sprint_start_date:
            return -1
        return 1

    @staticmethod
    def compare_status(a, b):
        if a.is_resolved and not b.is_resolved:
            return -1
        if b.is_resolved and not a.is_resolved:
            return 1
        if a.is_resolved and b.is_resolved:
            if a.resolved_at_date < b.resolved_at_date:
                return -1
            return 1
        return 0


def main():
    argpar = argparse.ArgumentParser()
    argpar.add_argument('-l', '--loglevel', default=DEFAULT_LOGLEVEL,
                        help='Level for logging (strings from logging python package)')
    argpar.add_argument('-q', '--query', required=True,
                        help='Query to perform on JIRA server')
    argpar.add_argument('-o', '--output', default=DEFAULT_OUTPUT,
                        help='Output .tjp file for task-juggler')
    argpar.add_argument('-L', '--links', nargs='*',
                        help="Specific issue link type inward/outward links to consider for TaskJuggler's 'depends' "
                        "keyword, e.g. 'depends on'. "
                        "By default, link types Dependency/Dependent (outward only) and Blocker/Blocks (inwardy only) "
                        "are considered.  Specify an empty value to ignore Jira issue links altogether.")
    argpar.add_argument('-D', '--depend-on-preceding', action='store_true',
                        help='Flag to let tasks depend on the preceding task with the same assignee')
    argpar.add_argument('-s', '--sort-on-sprint', dest='sprint_field_name', default='',
                        help='Sort unresolved tasks by using field name that stores sprint(s), e.g. customfield_10851, '
                             'in addition to the original order')
    argpar.add_argument('-w', '--weeklymax', default=5.0, type=float,
                        help='Number of allocated workdays per week used to approximate '
                             'start time of unresolved tasks with logged time')
    argpar.add_argument('-c', '--current-date', default=datetime.now(), type=parser.isoparse,
                        help='Specify the offset-naive date to use for calculation as current date. If no value is '
                             'specified, the current value of the system clock is used.')
    args = argpar.parse_args()
    set_logging_level(args.loglevel)

    user, token = fetch_credentials()
    endpoint = config('JIRA_API_ENDPOINT', default=DEFAULT_JIRA_URL)
    JUGGLER = JiraJuggler(endpoint, user, token, args.query, links=args.links)

    JUGGLER.juggle(
        output=args.output,
        depend_on_preceding=args.depend_on_preceding,
        sprint_field_name=args.sprint_field_name,
        weeklymax=args.weeklymax,
        current_date=args.current_date
    )
    return 0


def entrypoint():
    """Wrapper function of main"""
    raise SystemExit(main())


if __name__ == "__main__":
    entrypoint()
