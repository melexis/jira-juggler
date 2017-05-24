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
task {id} "{key}: {description}" {{
{props}
}}
'''

JUGGLER_TASK_PROPERTY_TEMPLATE = '    {prop} {value}\n'

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
            url URL to the JIRA server
            user Username on JIRA server
        '''

        logging.info('Jira server: %s', url)
        logging.info('Query: %s', query)

        password = getpass('Enter JIRA password for {user}: '.format(user=user))
        self.query = query
        self.jirahandle = JIRA(url, basic_auth=(user, password))
        self.issue_count = 0

    def get_issue_properties(self, issue):
        '''
        Convert JIRA issue properties to the task juggler syntax

        Args:
            issue The issue to work on
        Returns:
            String representation of the issue properties in juggler syntax
        '''
        props = ''
        props += JUGGLER_TASK_PROPERTY_TEMPLATE.format(prop='allocate', value=issue.fields.assignee)
        props += JUGGLER_TASK_PROPERTY_TEMPLATE.format(prop='effort', value=issue.fields.aggregatetimeoriginalestimate) #todo: this is seconds, convert to days
        for link in issue.fields.issuelinks:
            if hasattr(link, 'inwardIssue'): #is blocked by (TODO: other relations as well?)
                props += JUGGLER_TASK_PROPERTY_TEMPLATE.format(prop='depends', value=link.inwardIssue.key)
        return props

    def generate(self, output):
        '''
        Query JIRA and generate task-juggler output from given issues

        Args:
            output Name of output file, for task-juggler
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
                    out.write(JUGGLER_TASK_TEMPLATE.format(id=issue.key,
                                                           key=issue.key,
                                                           description=issue.fields.summary,
                                                           props=self.get_issue_properties(issue)))

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

