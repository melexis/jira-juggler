#!/usr/bin/python
# -*- coding: utf-8 -*-

import json
from collections import namedtuple

import unittest

try:
    from unittest.mock import MagicMock, patch, call
except ImportError:
    print("unittest.mock import failed")
    try:
        from mock import MagicMock, patch, call
    except ImportError:
        print("mock import failed. installing mock")
        import pip
        pip.main(['install', 'mock'])
        from mock import MagicMock, patch, call

import mlx.jira_juggler as dut

try:
    from jira import JIRA
except ImportError:
    print("jira import failed")
    import pip
    pip.main(['install', 'jira'])
    from jira import JIRA


class TestJiraJuggler(unittest.TestCase):
    '''
    Testing JiraJuggler interface

    todo:
        - Currently we only test the parsing part (parsing JIRA outcome), and assert the content of the internal
          data structures. We need to extend to test the outcoming text (file) which can be given to TaskJuggler.
    '''

    URL = 'http://my-non-existing-jira.melexis.com'
    USER = 'justme'
    PASSWD = 'myuselesspassword'
    QUERY = 'some random query'
    SECS_PER_DAY = 8.0 * 60 * 60

    KEY1 = 'Issue1'
    SUMMARY1 = 'Some random description of issue 1'
    ASSIGNEE1 = 'John Doe'
    ESTIMATE1 = 0.3 * SECS_PER_DAY
    DEPENDS1 = []

    KEY2 = 'Issue2'
    SUMMARY2 = 'Some random description of issue 2'
    ASSIGNEE2 = 'Jane Doe'
    ESTIMATE2 = 1.2 * SECS_PER_DAY
    DEPENDS2 = [KEY1]

    KEY3 = 'Issue3'
    SUMMARY3 = 'Some random description of issue 3'
    ASSIGNEE3 = 'Cooky Doe'
    ESTIMATE3 = 1.0 * SECS_PER_DAY
    DEPENDS3 = [KEY1, KEY2]

    JIRA_JSON_ASSIGNEE_TEMPLATE = '''
            "assignee": {{
                "name": "{assignee}"
            }}
    '''

    JIRA_JSON_ESTIMATE_TEMPLATE = '''
            "timeestimate": {estimate}
    '''

    JIRA_JSON_LINKS_TEMPLATE = '''
            "issuelinks": [
                {links}
            ]
    '''

    JIRA_JSON_DEPENDS_TEMPLATE = '''
                {{
                    "inwardIssue": {{
                        "key": "{depends}"
                    }},
                    "type": {{
                        "name": "Blocker"
                    }}
                }}
    '''

    JIRA_JSON_ISSUE_TEMPLATE = '''{{
        "key": "{key}",
        "fields": {{
            "summary": "{summary}"
            {properties}
        }}
    }}'''

    def SetUp(self):
        '''SetUp is run before each test to provide clean working environment'''

    @patch('mlx.jira_juggler.JIRA', autospec=True)
    def test_empty_query_result(self, jira_mock):
        '''Test for Jira not returning any task on the given query'''
        jira_mock_object = MagicMock(spec=JIRA)
        jira_mock.return_value = jira_mock_object
        juggler = dut.JiraJuggler(self.URL, self.USER, self.PASSWD, self.QUERY)
        self.assertEqual(self.QUERY, juggler.query)

        jira_mock_object.search_issues.return_value = []
        juggler.juggle()
        jira_mock_object.search_issues.assert_called_once_with(self.QUERY, maxResults=dut.JIRA_PAGE_SIZE, startAt=0)

    @patch('mlx.jira_juggler.JIRA', autospec=True)
    def test_single_task_happy(self, jira_mock):
        '''Test for simple happy flow: single task is returned by Jira'''
        jira_mock_object = MagicMock(spec=JIRA)
        jira_mock.return_value = jira_mock_object
        juggler = dut.JiraJuggler(self.URL, self.USER, self.PASSWD, self.QUERY)
        self.assertEqual(self.QUERY, juggler.query)

        jira_mock_object.search_issues.side_effect = [[self._mock_jira_issue(self.KEY1,
                                                                             self.SUMMARY1,
                                                                             self.ASSIGNEE1,
                                                                             self.ESTIMATE1,
                                                                             self.DEPENDS1)
                                                       ], []]
        issues = juggler.juggle()
        jira_mock_object.search_issues.assert_has_calls([call(self.QUERY, maxResults=dut.JIRA_PAGE_SIZE, startAt=0),
                                                         call(self.QUERY, maxResults=dut.JIRA_PAGE_SIZE, startAt=1)])
        self.assertEqual(1, len(issues))
        self.assertEqual(self.KEY1, issues[0].key)
        self.assertEqual(self.SUMMARY1, issues[0].summary)
        self.assertEqual(self.ASSIGNEE1, issues[0].properties['allocate'].value)
        self.assertEqual(self.ESTIMATE1 / self.SECS_PER_DAY, issues[0].properties['effort'].value)
        self.assertEqual(self.DEPENDS1, issues[0].properties['depends'].value)

    @patch('mlx.jira_juggler.JIRA', autospec=True)
    def test_single_task_minimal(self, jira_mock):
        '''Test for minimal happy flow: single task with minimal content is returned by Jira

        Note: the default effort is choosen.
        '''
        jira_mock_object = MagicMock(spec=JIRA)
        jira_mock.return_value = jira_mock_object
        juggler = dut.JiraJuggler(self.URL, self.USER, self.PASSWD, self.QUERY)
        self.assertEqual(self.QUERY, juggler.query)

        jira_mock_object.search_issues.side_effect = [[self._mock_jira_issue(self.KEY1,
                                                                             self.SUMMARY1)
                                                       ], []]
        issues = juggler.juggle()
        jira_mock_object.search_issues.assert_has_calls([call(self.QUERY, maxResults=dut.JIRA_PAGE_SIZE, startAt=0),
                                                         call(self.QUERY, maxResults=dut.JIRA_PAGE_SIZE, startAt=1)])
        self.assertEqual(1, len(issues))
        self.assertEqual(self.KEY1, issues[0].key)
        self.assertEqual(self.SUMMARY1, issues[0].summary)
        self.assertEqual(dut.JugglerTaskEffort.DEFAULT_VALUE, issues[0].properties['effort'].value)

    @patch('mlx.jira_juggler.JIRA', autospec=True)
    def test_estimate_too_low(self, jira_mock):
        '''Test for correcting an estimate which is too low'''
        jira_mock_object = MagicMock(spec=JIRA)
        jira_mock.return_value = jira_mock_object
        juggler = dut.JiraJuggler(self.URL, self.USER, self.PASSWD, self.QUERY)
        self.assertEqual(self.QUERY, juggler.query)

        jira_mock_object.search_issues.side_effect = [[self._mock_jira_issue(self.KEY1,
                                                                             self.SUMMARY1,
                                                                             estimate=1)
                                                       ], []]
        issues = juggler.juggle()
        jira_mock_object.search_issues.assert_has_calls([call(self.QUERY, maxResults=dut.JIRA_PAGE_SIZE, startAt=0),
                                                         call(self.QUERY, maxResults=dut.JIRA_PAGE_SIZE, startAt=1)])
        self.assertEqual(1, len(issues))
        self.assertEqual(self.KEY1, issues[0].key)
        self.assertEqual(self.SUMMARY1, issues[0].summary)
        self.assertEqual(dut.JugglerTaskEffort.MINIMAL_VALUE, issues[0].properties['effort'].value)

    @patch('mlx.jira_juggler.JIRA', autospec=True)
    def test_broken_depends(self, jira_mock):
        '''Test for removing a broken link to a dependant task'''
        jira_mock_object = MagicMock(spec=JIRA)
        jira_mock.return_value = jira_mock_object
        juggler = dut.JiraJuggler(self.URL, self.USER, self.PASSWD, self.QUERY)
        self.assertEqual(self.QUERY, juggler.query)

        jira_mock_object.search_issues.side_effect = [[self._mock_jira_issue(self.KEY1,
                                                                             self.SUMMARY1,
                                                                             depends=['non-existing-key-of-issue'])
                                                       ], []]
        issues = juggler.juggle()
        jira_mock_object.search_issues.assert_has_calls([call(self.QUERY, maxResults=dut.JIRA_PAGE_SIZE, startAt=0),
                                                         call(self.QUERY, maxResults=dut.JIRA_PAGE_SIZE, startAt=1)])
        self.assertEqual(1, len(issues))
        self.assertEqual(self.KEY1, issues[0].key)
        self.assertEqual(self.SUMMARY1, issues[0].summary)
        self.assertEqual([], issues[0].properties['depends'].value)

    @patch('mlx.jira_juggler.JIRA', autospec=True)
    def test_task_depends(self, jira_mock):
        '''Test for dual happy flow: one task depends on the other'''
        jira_mock_object = MagicMock(spec=JIRA)
        jira_mock.return_value = jira_mock_object
        juggler = dut.JiraJuggler(self.URL, self.USER, self.PASSWD, self.QUERY)
        self.assertEqual(self.QUERY, juggler.query)

        jira_mock_object.search_issues.side_effect = [[self._mock_jira_issue(self.KEY1,
                                                                             self.SUMMARY1,
                                                                             self.ASSIGNEE1,
                                                                             self.ESTIMATE1,
                                                                             self.DEPENDS1),
                                                       self._mock_jira_issue(self.KEY2,
                                                                             self.SUMMARY2,
                                                                             self.ASSIGNEE2,
                                                                             self.ESTIMATE2,
                                                                             self.DEPENDS2),
                                                       ], []]
        issues = juggler.juggle()
        jira_mock_object.search_issues.assert_has_calls([call(self.QUERY, maxResults=dut.JIRA_PAGE_SIZE, startAt=0),
                                                         call(self.QUERY, maxResults=dut.JIRA_PAGE_SIZE, startAt=2)])
        self.assertEqual(2, len(issues))
        self.assertEqual(self.KEY1, issues[0].key)
        self.assertEqual(self.SUMMARY1, issues[0].summary)
        self.assertEqual(self.ASSIGNEE1, issues[0].properties['allocate'].value)
        self.assertEqual(self.ESTIMATE1 / self.SECS_PER_DAY, issues[0].properties['effort'].value)
        self.assertEqual(self.DEPENDS1, issues[0].properties['depends'].value)
        self.assertEqual(self.KEY2, issues[1].key)
        self.assertEqual(self.SUMMARY2, issues[1].summary)
        self.assertEqual(self.ASSIGNEE2, issues[1].properties['allocate'].value)
        self.assertEqual(self.ESTIMATE2 / self.SECS_PER_DAY, issues[1].properties['effort'].value)
        self.assertEqual(self.DEPENDS2, issues[1].properties['depends'].value)

    @patch('mlx.jira_juggler.JIRA', autospec=True)
    def test_task_double_depends(self, jira_mock):
        '''Test for extended happy flow: one task depends on two others'''
        jira_mock_object = MagicMock(spec=JIRA)
        jira_mock.return_value = jira_mock_object
        juggler = dut.JiraJuggler(self.URL, self.USER, self.PASSWD, self.QUERY)
        self.assertEqual(self.QUERY, juggler.query)

        jira_mock_object.search_issues.side_effect = [[self._mock_jira_issue(self.KEY1,
                                                                             self.SUMMARY1,
                                                                             self.ASSIGNEE1,
                                                                             self.ESTIMATE1,
                                                                             self.DEPENDS1),
                                                       self._mock_jira_issue(self.KEY2,
                                                                             self.SUMMARY2,
                                                                             self.ASSIGNEE2,
                                                                             self.ESTIMATE2,
                                                                             self.DEPENDS2),
                                                       self._mock_jira_issue(self.KEY3,
                                                                             self.SUMMARY3,
                                                                             self.ASSIGNEE3,
                                                                             self.ESTIMATE3,
                                                                             self.DEPENDS3),
                                                       ], []]
        issues = juggler.juggle()
        jira_mock_object.search_issues.assert_has_calls([call(self.QUERY, maxResults=dut.JIRA_PAGE_SIZE, startAt=0),
                                                         call(self.QUERY, maxResults=dut.JIRA_PAGE_SIZE, startAt=3)])
        self.assertEqual(3, len(issues))
        self.assertEqual(self.KEY1, issues[0].key)
        self.assertEqual(self.SUMMARY1, issues[0].summary)
        self.assertEqual(self.ASSIGNEE1, issues[0].properties['allocate'].value)
        self.assertEqual(self.ESTIMATE1 / self.SECS_PER_DAY, issues[0].properties['effort'].value)
        self.assertEqual(self.DEPENDS1, issues[0].properties['depends'].value)
        self.assertEqual(self.KEY2, issues[1].key)
        self.assertEqual(self.SUMMARY2, issues[1].summary)
        self.assertEqual(self.ASSIGNEE2, issues[1].properties['allocate'].value)
        self.assertEqual(self.ESTIMATE2 / self.SECS_PER_DAY, issues[1].properties['effort'].value)
        self.assertEqual(self.DEPENDS2, issues[1].properties['depends'].value)
        self.assertEqual(self.KEY3, issues[2].key)
        self.assertEqual(self.SUMMARY3, issues[2].summary)
        self.assertEqual(self.ASSIGNEE3, issues[2].properties['allocate'].value)
        self.assertEqual(self.ESTIMATE3 / self.SECS_PER_DAY, issues[2].properties['effort'].value)
        self.assertEqual(self.DEPENDS3, issues[2].properties['depends'].value)

    def _mock_jira_issue(self, key, summary, assignee=None, estimate=None, depends=[]):
        '''
        Helper function to create a mocked Jira issue

        Args:
            key (str): Key of the mocked Jira issue
            summary (str): Summary of the mocked Jira issue
            assignee (str): Name of the assignee of the mocked Jira issue
            estimate (float): Number of estimated seconds of the mocked Jira issue
            depends (list): List of keys (str) of the issue on which the mocked Jira issue depends (blocked by relation)

        Returns:
            object: Mocked Jira Issue object
        '''
        props = ''
        if assignee:
            props += ', '
            props += self.JIRA_JSON_ASSIGNEE_TEMPLATE.format(assignee=assignee)
        if estimate:
            props += ', '
            props += self.JIRA_JSON_ESTIMATE_TEMPLATE.format(estimate=estimate)
        if depends:
            props += ', '
            deps = ''
            for dep in depends:
                if deps:
                    deps += ', '
                deps += self.JIRA_JSON_DEPENDS_TEMPLATE.format(depends=dep)
            props += self.JIRA_JSON_LINKS_TEMPLATE.format(links=deps)

        data = self.JIRA_JSON_ISSUE_TEMPLATE.format(key=key,
                                                    summary=summary,
                                                    properties=props)
        return json.loads(data, object_hook=lambda d: namedtuple('X', d.keys())(*d.values()))
