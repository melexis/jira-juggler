#! /usr/bin/python3

"""
Jira to task-juggler extraction script

This script queries Jira, and generates a task-juggler input file in order to generate a gant-chart.
"""

from getpass import getpass
import argparse
import logging
from jira import JIRA

DEFAULT_LOGLEVEL = 'warning'
DEFAULT_JIRA_URL = 'https://jira.melexis.com/jira'
DEFAULT_JIRA_USER = 'swcc'
DEFAULT_JIRA_QUERY = 'project = X AND fixVersion = Y'
DEFAULT_OUTPUT = 'jira_export.tjp'

JIRA_PAGE_SIZE = 50

TASKJUGGLER_PROPERTY_TRANSLATION = {
    'allocate': 'assignee',
    'effort': 'aggregatetimeoriginalestimate',
}

JUGGLER_TASK_TEMPLATE = '''
{tabulator}task {id} "{key}: {description}" {{
{props}
{tabulator}}}
'''

JUGGLER_PARENT_TASK_TEMPLATE_START = '''
{tabulator}task {id} "{key}: {description}" {{
'''
JUGGLER_PARENT_TASK_TEMPLATE_END = '''
{tabulator}}}
'''

JUGGLER_TASK_PROPERTY_TEMPLATE = '{tabulator}{prop} {value}\n'

TAB = '\t'

def set_logging_level(loglevel):
    '''
    Set the logging level

    Args:
        loglevel String representation of the loglevel
    '''
    numeric_level = getattr(logging, loglevel.upper(), None)
    if not isinstance(numeric_level, int):
        raise ValueError('Invalid log level: %s' % loglevel)
    logging.basicConfig(level=numeric_level)

class JiraJuggler(object):

    '''Class for task-juggling Jira results'''

    def __init__(self, url, user, query):
        '''
        Construct a JIRA juggler object

        Args:
            url (str): URL to the JIRA server
            user (str): Username on JIRA server
            query (str): The Query to run on JIRA server
        '''

        logging.info('Jira server: %s', url)
        logging.info('Query: %s', query)

        password = getpass('Enter JIRA password for {user}: '.format(user=user))
        self.query = query
        self.jirahandle = JIRA(url, basic_auth=(user, password))
        self.issue_count = 0

    @staticmethod
    def get_issue_properties(issue, tabulator=''):
        '''
        Convert JIRA issue properties to the task juggler syntax

        Args:
            issue: The issue to work on

        Returns:
            str: String representation of the issue properties in juggler syntax
        '''
        props = ''
        if hasattr(issue.fields, 'assignee'):
            props += JUGGLER_TASK_PROPERTY_TEMPLATE.format(tabulator=tabulator,
                                                           prop='allocate',
                                                           value=issue.fields.assignee.name)
        if hasattr(issue.fields, 'aggregatetimeoriginalestimate') and issue.fields.aggregatetimeoriginalestimate:
            props += JUGGLER_TASK_PROPERTY_TEMPLATE.format(tabulator=tabulator,
                                                           prop='effort',
                                                           value=str(issue.fields.aggregatetimeoriginalestimate/(8.0*60*60))+'d')
        else:
            logging.warning('No estimate found for %s, assuming 1 day', issue.key)
            props += JUGGLER_TASK_PROPERTY_TEMPLATE.format(tabulator=tabulator, prop='effort', value='1d')
        if hasattr(issue.fields, 'issuelinks'):
            for link in issue.fields.issuelinks:
                if hasattr(link, 'inwardIssue') and link.type.name == 'Blocker':
                    props += JUGGLER_TASK_PROPERTY_TEMPLATE.format(tabulator=tabulator,
                                                                   prop='depends',
                                                                   value='!'+link.inwardIssue.key.replace('-', '_'))
        return props

    def get_issue_string(self, issue, tabulator=''):
        '''
        Convert JIRA issue to the task juggler syntax

        Args:
            issue: The issue to work on

        Returns:
            str: String representation of the issue in juggler syntax
        '''
        issue_string = ''
        children = self.get_subtasks(issue)
        if children:
            issue_string += JUGGLER_PARENT_TASK_TEMPLATE_START.format(tabulator=tabulator,
                                                                      id=issue.key.replace('-', '_'),
                                                                      key=issue.key,
                                                                      description=issue.fields.summary.replace('\"', '\\\"'))
            for child in children:
                child_issue = self.jirahandle.issue(child.key)
                issue_string += self.get_issue_string(child_issue, tabulator=tabulator+TAB)
            issue_string += JUGGLER_PARENT_TASK_TEMPLATE_END.format(tabulator=tabulator)

        elif not self.is_child(issue) or tabulator == TAB:
            issue_string += JUGGLER_TASK_TEMPLATE.format(tabulator=tabulator,
                                                         id=issue.key.replace('-', '_'),
                                                         key=issue.key,
                                                         description=issue.fields.summary.replace('\"', '\\\"'),
                                                         props=self.get_issue_properties(issue, tabulator=tabulator+TAB))
        return issue_string

    @staticmethod
    def get_subtasks(issue):
        '''
        Check whether a ticket is a parent-task

        Args:
            issue: The parent issue to look for sub-tasks

        Returns:
            list: A list of sub-tasks if any, None otherwise.
        '''
        if hasattr(issue.fields, 'subtasks'):
            return issue.fields.subtasks
        return None

    @staticmethod
    def is_child(issue):
        '''
        Check whether a ticket is a child-task

        Args:
            issue: The issue to check

        Returns:
            bool: True if the given issue is a child-task, False otherwise.
        '''
        return hasattr(issue.fields, 'parent') and issue.fields.parent

    def generate(self, output):
        '''
        Query JIRA and generate task-juggler output from given issues

        Args:
            output (str): Name of output file, for task-juggler
        '''
        with open(output, 'w') as out:
            busy = True
            while busy:
                try:
                    issues = self.jirahandle.search_issues(self.query, maxResults=JIRA_PAGE_SIZE, startAt=self.issue_count)
                except:
                    logging.error('No Jira issues found for query "%s", is this correct?', self.query)
                    busy = False

                if not len(issues):
                    busy = False

                self.issue_count += len(issues)

                for issue in issues:
                    logging.debug('%s: %s', issue.key, issue.fields.summary)
                    out.write(self.get_issue_string(issue))

if __name__ == "__main__":
    ARGPARSER = argparse.ArgumentParser()
    ARGPARSER.add_argument('-l', '--loglevel', dest='loglevel', default=DEFAULT_LOGLEVEL,
                           action='store', required=False,
                           help='Level for logging (strings from logging python package)')
    ARGPARSER.add_argument('-j', '--jira', dest='url', default=DEFAULT_JIRA_URL,
                           action='store', required=False,
                           help='URL to JIRA server')
    ARGPARSER.add_argument('-u', '--username', dest='username', default=DEFAULT_JIRA_USER,
                           action='store', required=True,
                           help='Your username on JIRA server')
    ARGPARSER.add_argument('-q', '--query', dest='query', default=DEFAULT_JIRA_QUERY,
                           action='store', required=True,
                           help='Query to perform on JIRA server')
    ARGPARSER.add_argument('-o', '--output', dest='output', default=DEFAULT_OUTPUT,
                           action='store', required=False,
                           help='Output .tjp file for task-juggler')
    ARGS = ARGPARSER.parse_args()

    set_logging_level(ARGS.loglevel)

    JUGGLER = JiraJuggler(ARGS.url, ARGS.username, ARGS.query)

    JUGGLER.generate(ARGS.output)

