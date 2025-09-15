#!/usr/bin/python
# -*- coding: utf-8 -*-

import json
from datetime import datetime
from types import SimpleNamespace

from dateutil import parser
from parameterized import parameterized
from collections import namedtuple

import unittest

try:
    from unittest.mock import MagicMock, patch
except ImportError:
    print("unittest.mock import failed")
    try:
        from mock import MagicMock, patch
    except ImportError:
        print("mock import failed. installing mock")
        import pip
        pip.main(['install', 'mock'])
        from mock import MagicMock, patch

import mlx.jira_juggler.jira_juggler as dut

try:
    from jira import JIRA
except ImportError:
    print("jira import failed")
    import pip
    pip.main(['install', 'jira'])
    from jira import JIRA


LinkType = namedtuple('LinkType', 'id name inward outward self')
ISSUE_LINK_TYPES = [
    LinkType(
        id="1000",
        name="Duplicate",
        inward="is duplicated by",
        outward="duplicates",
        self="http://www.example.com/jira/rest/api/2//issueLinkType/1000",
    ),
    LinkType(
        id="1010",
        name="Blocker",
        inward="is blocked by",
        outward="blocks",
        self="http://www.example.com/jira/rest/api/2//issueLinkType/1010",
    ),
    LinkType(
        id="1050",
        name="Dependency",
        inward="is dependency of",
        outward="depends on",
        self="http://www.example.com/jira/rest/api/2//issueLinkType/1050",
    ),
]


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

    KEY1 = 'Issue-1'
    ID1 = 'Issue_1'
    SUMMARY1 = 'Some random description of issue 1'
    ASSIGNEE1 = 'John Doe'
    EMAIL1 = 'jod@gmail.com'
    USERNAME1 = 'jod'
    ESTIMATE1 = 0.3 * SECS_PER_DAY
    DEPENDS1 = []

    KEY2 = 'Issue-2'
    ID2 = 'Issue_2'
    SUMMARY2 = 'Some random description of issue 2'
    ASSIGNEE2 = 'Jane Doe'
    EMAIL2 = 'jad@gmail.com'
    USERNAME2 = 'jad'
    ESTIMATE2 = 1.2 * SECS_PER_DAY
    DEPENDS2 = [ID1]

    KEY3 = 'Issue-3'
    ID3 = 'Issue_3'
    SUMMARY3 = 'Some random description of issue 3'
    ASSIGNEE3 = 'Cooky Doe'
    EMAIL3 = 'cod@gmail.com'
    USERNAME3 = 'cod'
    ESTIMATE3 = 1.0 * SECS_PER_DAY
    DEPENDS3 = [ID1, ID2]

    JIRA_JSON_ASSIGNEE_TEMPLATE = '''
            "assignee": {{
                "name": "{assignee}"
            }}
    '''
    JIRA_CLOUD_JSON_ASSIGNEE_TEMPLATE = '''
            "assignee": {{
                "emailAddress": "{email}",
                "displayName": "{assignee}",
                "accountId": "{account_id}"
            }}
    '''

    JIRA_JSON_ESTIMATE_TEMPLATE = '''
            "timeoriginalestimate": {},
            "timespent": {},
            "timeestimate": {}
    '''

    JIRA_JSON_STATUS_TEMPLATE = '''
            "status": {{
                "name": "{status}"
            }}
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
                        "name": "Blocker",
                        "id": "1010",
                        "inward": "is blocked by",
                        "outward": "blocks"
                    }}
                }}
    '''

    JIRA_JSON_HISTORY_TEMPLATE = '''
                {{
                    "histories": [{'items': [{'field': 'status',
                                              'toString': '{new_status}'}]}]
                }}
    '''

    JIRA_JSON_ISSUE_TEMPLATE = '''{{
        "key": "{key}",
        "changelog": {changelog},

        "fields": {{
            "summary": "{summary}"
            {properties}
        }}
    }}'''

    # Templates for epic and hierarchy testing
    JIRA_JSON_ISSUETYPE_TEMPLATE = '''
            "issuetype": {{
                "name": "{issue_type}",
                "subtask": {is_subtask}
            }}
    '''

    JIRA_JSON_PARENT_TEMPLATE = '''
            "parent": {{
                "key": "{parent_key}"
            }}
    '''

    JIRA_JSON_EPIC_TEMPLATE = '''
            "customfield_10014": {{
                "key": "{epic_key}"
            }}
    '''

    def setUp(self):
        '''setUp is run before each test to provide clean working environment'''
        # Initialize global variables that the module expects
        dut.id_to_username_mapping = {}

    @patch('mlx.jira_juggler.jira_juggler.JIRA', autospec=True)
    def test_empty_query_result(self, jira_mock):
        '''Test for Jira not returning any task on the given query'''
        jira_mock_object = MagicMock(spec=JIRA)
        jira_mock.return_value = jira_mock_object
        juggler = dut.JiraJuggler(self.URL, self.USER, self.PASSWD, self.QUERY)
        self.assertEqual(self.QUERY, juggler.query)

        jira_mock_object.enhanced_search_issues.return_value = []
        juggler.juggle()
        jira_mock_object.enhanced_search_issues.assert_called_once()

    @patch('mlx.jira_juggler.jira_juggler.JIRA', autospec=True)
    def test_single_task_happy(self, jira_mock):
        '''Test for simple happy flow: single task is returned by Jira Server'''
        jira_mock_object = MagicMock(spec=JIRA)
        jira_mock.return_value = jira_mock_object
        juggler = dut.JiraJuggler(self.URL, self.USER, self.PASSWD, self.QUERY)
        self.assertEqual(self.QUERY, juggler.query)

        jira_mock_object.enhanced_search_issues.side_effect = [
            [
                self._mock_jira_issue(
                    self.KEY1,
                    self.SUMMARY1,
                    self.ASSIGNEE1,
                    [self.ESTIMATE1, None, None],
                    self.DEPENDS1,
                )
            ],
            [],
        ]
        issues = juggler.juggle()
        self.assertEqual(jira_mock_object.enhanced_search_issues.call_count, 1)
        self.assertEqual(1, len(issues))
        self.assertEqual(self.KEY1, issues[0].key)
        self.assertEqual(self.SUMMARY1, issues[0].summary)
        self.assertEqual(self.ASSIGNEE1, issues[0].properties['allocate'].value)
        self.assertEqual(self.ESTIMATE1 / self.SECS_PER_DAY, issues[0].properties['effort'].value)
        self.assertEqual(self.DEPENDS1, issues[0].properties['depends'].value)

    @patch('mlx.jira_juggler.jira_juggler.JIRA', autospec=True)
    def test_single_task_email_happy(self, jira_mock):
        '''Test for simple happy flow: single task is returned by Jira Cloud'''
        jira_mock_object = MagicMock(spec=JIRA)
        jira_mock.return_value = jira_mock_object
        juggler = dut.JiraJuggler(self.URL, self.USER, self.PASSWD, self.QUERY)
        self.assertEqual(self.QUERY, juggler.query)

        jira_mock_object.enhanced_search_issues.side_effect = [
            [
                self._mock_jira_issue(
                    self.KEY1,
                    self.SUMMARY1,
                    self.ASSIGNEE1,
                    [self.ESTIMATE1, None, None],
                    self.DEPENDS1,
                    email=self.EMAIL1,
                )
            ],
            [],
        ]
        issues = juggler.juggle()
        self.assertEqual(jira_mock_object.enhanced_search_issues.call_count, 1)
        self.assertEqual(1, len(issues))
        self.assertEqual(self.KEY1, issues[0].key)
        self.assertEqual(self.SUMMARY1, issues[0].summary)
        self.assertEqual(self.USERNAME1, issues[0].properties['allocate'].value)
        self.assertEqual(self.ESTIMATE1 / self.SECS_PER_DAY, issues[0].properties['effort'].value)
        self.assertEqual(self.DEPENDS1, issues[0].properties['depends'].value)

    @patch('mlx.jira_juggler.jira_juggler.JIRA', autospec=True)
    def test_single_task_email_hidden(self, jira_mock):
        '''Test for error logging when user has restricted email visibility in Jira Cloud'''
        jira_mock_object = MagicMock(spec=JIRA)
        jira_mock.return_value = jira_mock_object
        juggler = dut.JiraJuggler(self.URL, self.USER, self.PASSWD, self.QUERY)
        self.assertEqual(self.QUERY, juggler.query)

        mocked_issue = self._mock_jira_issue(self.KEY1,
                                             self.SUMMARY1,
                                             self.ASSIGNEE1,
                                             [self.ESTIMATE1, None, None],
                                             self.DEPENDS1,
                                             email=self.EMAIL1)
        mocked_issue.fields.assignee.emailAddress = ''
        jira_mock_object.enhanced_search_issues.side_effect = [
            [
                mocked_issue,
            ],
            [],
        ]
        issues = juggler.juggle()
        self.assertEqual(jira_mock_object.enhanced_search_issues.call_count, 1)
        self.assertEqual(1, len(issues))
        self.assertEqual(self.KEY1, issues[0].key)
        self.assertEqual(self.SUMMARY1, issues[0].summary)
        self.assertEqual(f'"{self.ASSIGNEE1}"', issues[0].properties['allocate'].value)
        self.assertEqual(self.ESTIMATE1 / self.SECS_PER_DAY, issues[0].properties['effort'].value)
        self.assertEqual(self.DEPENDS1, issues[0].properties['depends'].value)

    @patch('mlx.jira_juggler.jira_juggler.JIRA', autospec=True)
    def test_single_task_minimal(self, jira_mock):
        '''Test for minimal happy flow: single task with minimal content is returned by Jira

        Note: the default effort is choosen.
        '''
        jira_mock_object = MagicMock(spec=JIRA)
        jira_mock.return_value = jira_mock_object
        juggler = dut.JiraJuggler(self.URL, self.USER, self.PASSWD, self.QUERY)
        self.assertEqual(self.QUERY, juggler.query)

        jira_mock_object.enhanced_search_issues.side_effect = [
            [
                self._mock_jira_issue(
                    self.KEY1,
                    self.SUMMARY1,
                )
            ],
            [],
        ]
        issues = juggler.juggle()
        self.assertEqual(jira_mock_object.enhanced_search_issues.call_count, 1)
        self.assertEqual(1, len(issues))
        self.assertEqual(self.KEY1, issues[0].key)
        self.assertEqual(self.SUMMARY1, issues[0].summary)
        self.assertEqual(dut.JugglerTaskEffort.DEFAULT_VALUE, issues[0].properties['effort'].value)

    @patch('mlx.jira_juggler.jira_juggler.JIRA', autospec=True)
    def test_estimate_too_low(self, jira_mock):
        '''Test for correcting an estimate which is too low'''
        jira_mock_object = MagicMock(spec=JIRA)
        jira_mock.return_value = jira_mock_object
        juggler = dut.JiraJuggler(self.URL, self.USER, self.PASSWD, self.QUERY)
        self.assertEqual(self.QUERY, juggler.query)

        jira_mock_object.enhanced_search_issues.side_effect = [
            [
                self._mock_jira_issue(
                    self.KEY1,
                    self.SUMMARY1,
                    estimates=[1, None, None],
                )
            ],
            [],
        ]
        issues = juggler.juggle()
        self.assertEqual(jira_mock_object.enhanced_search_issues.call_count, 1)
        self.assertEqual(1, len(issues))
        self.assertEqual(self.KEY1, issues[0].key)
        self.assertEqual(self.SUMMARY1, issues[0].summary)
        self.assertEqual(dut.JugglerTaskEffort.MINIMAL_VALUE, issues[0].properties['effort'].value)

    @patch('mlx.jira_juggler.jira_juggler.JIRA', autospec=True)
    def test_broken_depends(self, jira_mock):
        '''Test for removing a broken link to a dependant task'''
        jira_mock_object = MagicMock(spec=JIRA)
        jira_mock.return_value = jira_mock_object
        jira_mock_object.issue_link_types.return_value = ISSUE_LINK_TYPES
        juggler = dut.JiraJuggler(self.URL, self.USER, self.PASSWD, self.QUERY)
        self.assertEqual(self.QUERY, juggler.query)

        jira_mock_object.enhanced_search_issues.side_effect = [
            [
                self._mock_jira_issue(
                    self.KEY1,
                    self.SUMMARY1,
                    depends=['non-existing-key-of-issue'],
                )
            ],
            [],
        ]
        issues = juggler.juggle()
        self.assertEqual(jira_mock_object.enhanced_search_issues.call_count, 1)
        self.assertEqual(1, len(issues))
        self.assertEqual(self.KEY1, issues[0].key)
        self.assertEqual(self.SUMMARY1, issues[0].summary)
        self.assertEqual([], issues[0].properties['depends'].value)

    @patch('mlx.jira_juggler.jira_juggler.JIRA', autospec=True)
    def test_task_depends(self, jira_mock):
        '''Test for dual happy flow: one task depends on the other'''
        jira_mock_object = MagicMock(spec=JIRA)
        jira_mock.return_value = jira_mock_object
        jira_mock_object.issue_link_types.return_value = ISSUE_LINK_TYPES
        juggler = dut.JiraJuggler(self.URL, self.USER, self.PASSWD, self.QUERY)
        self.assertEqual(self.QUERY, juggler.query)

        jira_mock_object.enhanced_search_issues.side_effect = [
            [
                self._mock_jira_issue(
                    self.KEY1,
                    self.SUMMARY1,
                    self.ASSIGNEE1,
                    [self.ESTIMATE1, None, None],
                    self.DEPENDS1,
                ),
                self._mock_jira_issue(
                    self.KEY2,
                    self.SUMMARY2,
                    self.ASSIGNEE2,
                    [self.ESTIMATE2, None, None],
                    self.DEPENDS2,
                ),
            ],
            [],
        ]
        issues = juggler.juggle()
        self.assertEqual(jira_mock_object.enhanced_search_issues.call_count, 1)
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

    @patch('mlx.jira_juggler.jira_juggler.JIRA', autospec=True)
    def test_task_double_depends(self, jira_mock):
        '''Test for extended happy flow: one task depends on two others'''
        jira_mock_object = MagicMock(spec=JIRA)
        jira_mock.return_value = jira_mock_object
        jira_mock_object.issue_link_types.return_value = ISSUE_LINK_TYPES
        juggler = dut.JiraJuggler(self.URL, self.USER, self.PASSWD, self.QUERY)
        self.assertEqual(self.QUERY, juggler.query)

        jira_mock_object.enhanced_search_issues.side_effect = [
            [
                self._mock_jira_issue(
                    self.KEY1,
                    self.SUMMARY1,
                    self.ASSIGNEE1,
                    [self.ESTIMATE1, None, None],
                    self.DEPENDS1,
                ),
                self._mock_jira_issue(
                    self.KEY2,
                    self.SUMMARY2,
                    self.ASSIGNEE2,
                    [self.ESTIMATE2, None, None],
                    self.DEPENDS2,
                ),
                self._mock_jira_issue(
                    self.KEY3,
                    self.SUMMARY3,
                    self.ASSIGNEE3,
                    [self.ESTIMATE3, None, None],
                    self.DEPENDS3,
                ),
            ],
            [],
        ]
        issues = juggler.juggle()
        self.assertEqual(jira_mock_object.enhanced_search_issues.call_count, 1)
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

    @patch('mlx.jira_juggler.jira_juggler.JIRA', autospec=True)
    def test_resolved_task(self, jira_mock):
        '''Test that the last assignee in the Analyzed state is used and the Time Spent is used as effort
        Test that the most recent transition to the Approved/Resolved state is used to mark the end'''
        jira_mock_object = MagicMock(spec=JIRA)
        jira_mock.return_value = jira_mock_object
        jira_mock_object.issue_link_types.return_value = ISSUE_LINK_TYPES
        juggler = dut.JiraJuggler(self.URL, self.USER, self.PASSWD, self.QUERY)
        histories = [
            {
                'items': [{
                    'field': 'assignee',
                    'to': self.ASSIGNEE1,
                }],
                'created': '2022-04-08T13:11:47.749+0200',
            },
            {
                'items': [{
                    'field': 'status',
                    'toString': 'Resolved',
                }],
                'created': '2022-04-11T08:13:14.350+0200',
            },
            {
                'items': [{
                    'field': 'assignee',
                    'to': self.ASSIGNEE3,
                    # 'from': self.ASSIGNEE1,  # cannot use 'from' as key to test
                }],
                'created': '2022-04-12T13:04:11.449+0200',
            },
            {
                'items': [{
                    'field': 'status',
                    'toString': 'Analyzed',
                }],
                'created': '2022-04-13T14:10:43.632+0200',
            },
            {
                'items': [{
                    'field': 'assignee',
                    'to': self.ASSIGNEE2,
                }],
                'created': '2022-05-02T09:20:36.310+0200',
            },
            {
                'items': [{
                    'field': 'status',
                    'toString': 'Approved',
                }],
                'created': '2022-05-25T14:07:11.974+0200',
            },
        ]
        jira_mock_object.enhanced_search_issues.side_effect = [[
            self._mock_jira_issue(
                self.KEY1,
                self.SUMMARY1,
                self.ASSIGNEE1,
                [self.ESTIMATE1, self.ESTIMATE2, self.ESTIMATE3],
                self.DEPENDS1,
                histories=histories,
                status="Resolved",
            ),
        ], []]
        issues = juggler.juggle()
        jira_mock_object.enhanced_search_issues.assert_called()
        self.assertEqual(1, len(issues))
        self.assertEqual(self.ASSIGNEE2, issues[0].properties['allocate'].value)
        self.assertEqual(self.ESTIMATE2 / self.SECS_PER_DAY, issues[0].properties['effort'].value)
        self.assertEqual('2022-05-25 14:07:11.974000+02:00', str(issues[0].resolved_at_date))

    @patch('mlx.jira_juggler.jira_juggler.JIRA', autospec=True)
    def test_closed_task(self, jira_mock):
        '''
        Test that a change of assignee after Resolved status has no effect and that the original time estimate is
        used when no time has been logged.
        '''
        jira_mock_object = MagicMock(spec=JIRA)
        jira_mock.return_value = jira_mock_object
        jira_mock_object.issue_link_types.return_value = ISSUE_LINK_TYPES
        juggler = dut.JiraJuggler(self.URL, self.USER, self.PASSWD, self.QUERY)
        histories = [
            {
                'items': [{
                    'field': 'status',
                    'toString': 'Resolved',
                }],
                'created': '2022-04-12T13:04:11.449+0200',
            },
            {
                'items': [{
                    'field': 'assignee',
                    'to': self.ASSIGNEE2,
                }],
                'created': '2022-05-25T14:07:11.974+0200',
            },
        ]

        jira_mock_object.enhanced_search_issues.side_effect = [[
            self._mock_jira_issue(
                self.KEY1,
                self.SUMMARY1,
                self.ASSIGNEE1,
                [self.ESTIMATE1, None, self.ESTIMATE3],
                self.DEPENDS1,
                histories=histories,
                status="Closed",
            ),
        ], []]
        issues = juggler.juggle()
        jira_mock_object.enhanced_search_issues.assert_called()
        self.assertEqual(1, len(issues))
        self.assertEqual(self.ASSIGNEE1, issues[0].properties['allocate'].value)
        self.assertEqual(self.ESTIMATE1 / self.SECS_PER_DAY, issues[0].properties['effort'].value)

    @patch('mlx.jira_juggler.jira_juggler.JIRA', autospec=True)
    def test_depend_on_preceding(self, jira_mock):
        '''Test --depends-on-preceding, --weeklymax and --current-date options'''
        jira_mock_object = MagicMock(spec=JIRA)
        jira_mock.return_value = jira_mock_object
        jira_mock_object.issue_link_types.return_value = ISSUE_LINK_TYPES
        juggler = dut.JiraJuggler(self.URL, self.USER, self.PASSWD, self.QUERY)
        histories = [
            {
                'created': '2021-08-18T18:30:15.338+0200',
                'items': [{
                    'field': 'status',
                    'toString': 'Resolved',
                }]
            },
        ]

        jira_mock_object.enhanced_search_issues.side_effect = [[
            self._mock_jira_issue(
                self.KEY1,
                self.SUMMARY1,
                self.ASSIGNEE1,
                [self.ESTIMATE1, None, None],
                self.DEPENDS1,
                histories=histories,
                status="Resolved",
            ),
            self._mock_jira_issue(
                self.KEY2,
                self.SUMMARY2,
                self.ASSIGNEE1,
                [self.SECS_PER_DAY * val for val in [5, 3.2, 2.4]],
                self.DEPENDS1,
                status="Open",
            ),
            self._mock_jira_issue(
                self.KEY3,
                self.SUMMARY3,
                self.ASSIGNEE1,
                [self.ESTIMATE2, None, self.ESTIMATE3],
                self.DEPENDS2,
                status="Open",
            ),
            self._mock_jira_issue(
                'Different-assignee',
                self.SUMMARY3,
                self.ASSIGNEE2,
                [self.ESTIMATE1, None, None],
                self.DEPENDS1,
                status="Open",
            ),
            self._mock_jira_issue(
                'Last-assignee',
                self.SUMMARY3,
                self.ASSIGNEE3,
                [self.ESTIMATE1, None, None],
                [self.KEY1, self.KEY2],
                status="Open",
            ),
        ], []]
        issues = juggler.juggle(depend_on_preceding=True, weeklymax=1.0, current_date=parser.isoparse('2021-08-23T13:30'))
        jira_mock_object.enhanced_search_issues.assert_called()
        self.assertEqual(5, len(issues))
        self.assertEqual(self.ASSIGNEE1, issues[0].properties['allocate'].value)
        self.assertEqual(self.ESTIMATE1 / self.SECS_PER_DAY, issues[0].properties['effort'].value)
        self.assertEqual('    end 2021-08-18-18:00-+0200\n', str(issues[0].properties['time']))
        self.assertEqual('', str(issues[0].properties['depends']))

        self.assertEqual(self.ASSIGNEE1, issues[1].properties['allocate'].value)
        self.assertEqual(3.2 + 2.4, issues[1].properties['effort'].value)
        self.assertEqual('    start %{2021-08-23-13:00 - 9.125d}\n', str(issues[1].properties['time']))  # 3.2 days spent
        self.assertEqual('', str(issues[1].properties['depends']))

        self.assertEqual(self.ASSIGNEE1, issues[2].properties['allocate'].value)
        self.assertEqual(self.ESTIMATE3 / self.SECS_PER_DAY, issues[2].properties['effort'].value)
        self.assertEqual(f'    depends !{self.ID1}, !{self.ID2}\n', str(issues[2].properties['depends']))

        self.assertEqual('', str(issues[3].properties['depends']))
        self.assertEqual('    start 2021-08-23-13:00\n', str(issues[3].properties['time']))  # start on current date

        self.assertEqual(f'    depends !{self.ID1}, !{self.ID2}\n', str(issues[4].properties['depends']))
        self.assertEqual('', str(issues[4].properties['time']))  # no start date as it depends on an unresolved task

    def _mock_jira_issue(self, key, summary, assignee='', estimates=[], depends=[], histories=[], status="Open", email='', issue_type='Task', parent_key=None, epic_key=None):
        '''
        Helper function to create a mocked Jira issue

        Args:
            key (str): Key of the mocked Jira issue
            summary (str): Summary of the mocked Jira issue
            assignee (str): Name of the assignee of the mocked Jira issue
            estimates (list): List of numbers of estimated seconds of the mocked Jira issue
                (original estimate, time spent, time remaining)
            depends (list): List of keys (str) of the issue on which the mocked Jira issue depends (blocked by relation)
            issue_type (str): Issue type name (Epic, Task, Sub-task, etc.)
            parent_key (str): Key of parent issue (for subtasks)
            epic_key (str): Key of epic issue

        Returns:
            object: Mocked Jira Issue object
        '''
        props = ', ' + self.JIRA_JSON_STATUS_TEMPLATE.format(status=status)
        if assignee:
            props += ', '
            if email:
                props += self.JIRA_CLOUD_JSON_ASSIGNEE_TEMPLATE.format(email=email, assignee=assignee,
                                                                       account_id=id(email))
            else:
                props += self.JIRA_JSON_ASSIGNEE_TEMPLATE.format(assignee=assignee)
        if estimates:
            # Pad to 3 slots: (timeoriginalestimate, timespent, timeestimate)
            while len(estimates) < 3:
                estimates.append(None)
            estimates = ['null' if val is None else val for val in estimates]
            props += ', '
            props += self.JIRA_JSON_ESTIMATE_TEMPLATE.format(*estimates)
        if depends:
            props += ', '
            deps = ''
            for dep in depends:
                if deps:
                    deps += ', '
                deps += self.JIRA_JSON_DEPENDS_TEMPLATE.format(depends=dep)
            props += self.JIRA_JSON_LINKS_TEMPLATE.format(links=deps)

        # Add issue type information
        is_subtask = 'true' if issue_type.lower() == 'sub-task' else 'false'
        props += ', ' + self.JIRA_JSON_ISSUETYPE_TEMPLATE.format(issue_type=issue_type, is_subtask=is_subtask)

        # Add parent relationship for subtasks
        if parent_key:
            props += ', ' + self.JIRA_JSON_PARENT_TEMPLATE.format(parent_key=parent_key)

        # Add epic link
        if epic_key:
            props += ', ' + self.JIRA_JSON_EPIC_TEMPLATE.format(epic_key=epic_key)

        changelog = '{{"histories": {}}}'.format(json.dumps(histories))

        data = self.JIRA_JSON_ISSUE_TEMPLATE.format(key=key,
                                                    summary=summary,
                                                    properties=props,
                                                    changelog=changelog)
        return json.loads(data, object_hook=lambda d: SimpleNamespace(**d))

    @parameterized.expand([
        ("2021-08-15-11:00", 10, 5, 2),
        ("2021-08-22-11:00", 10, 5, 2),
        ("2021-08-23-11:00", 10, 5, 2),
        ("2021-08-23-09:00", 5, 5.0, 2),
        ("2021-08-23-09:01", 5, 5.0, 1),
        ("2021-08-23-13:00", 5.5, 5.0, 2),
        ("2021-08-23-13:01", 5.5, 5.0, 1),
        ("2021-08-23-13:00", 0.2, 0.1, 2),
        ("2021-08-23-10:00", 0, 0, 0),
        ("2021-08-14-10:00", 0, 0, 0),
    ])
    def test_calculate_weekends(self, date_str, workdays_passed, weeklymax, ref_output):
        date = datetime.strptime(date_str, '%Y-%m-%d-%H:%M')
        output = dut.calculate_weekends(date, workdays_passed, weeklymax)
        self.assertEqual(output, ref_output)

    @patch('mlx.jira_juggler.jira_juggler.JIRA', autospec=True)
    def test_epic_hierarchy_detection(self, jira_mock):
        """Test detection of epic and parent-child relationships"""
        # Create mock issues: Epic -> Story -> Subtask
        epic_issue = self._mock_jira_issue('EPIC-1', 'Epic Issue', 'testuser', [3 * self.SECS_PER_DAY, None, None],
                                           issue_type='Epic')
        story_issue = self._mock_jira_issue('STORY-1', 'Story Issue', 'testuser', [1 * self.SECS_PER_DAY, None, None],
                                            epic_key='EPIC-1', issue_type='Story')
        subtask_issue = self._mock_jira_issue('SUB-1', 'Subtask Issue', 'testuser', [0.5 * self.SECS_PER_DAY, None, None],
                                              parent_key='STORY-1', issue_type='Sub-task')

        jirahandle = jira_mock.return_value
        jirahandle.enhanced_search_issues.return_value = [epic_issue, story_issue, subtask_issue]
        jirahandle.issue_link_types.return_value = ISSUE_LINK_TYPES

        # Test individual task hierarchy detection
        epic_task = dut.JugglerTask(epic_issue)
        story_task = dut.JugglerTask(story_issue)
        subtask_task = dut.JugglerTask(subtask_issue)

        # Verify epic detection
        self.assertTrue(epic_task.is_epic)
        self.assertFalse(epic_task.is_subtask)
        self.assertIsNone(epic_task.epic_key)
        self.assertIsNone(epic_task.parent_key)

        # Verify story detection (child of epic)
        self.assertFalse(story_task.is_epic)
        self.assertFalse(story_task.is_subtask)
        self.assertEqual(story_task.epic_key, 'EPIC-1')
        self.assertIsNone(story_task.parent_key)

        # Verify subtask detection (child of story)
        self.assertFalse(subtask_task.is_epic)
        self.assertTrue(subtask_task.is_subtask)
        self.assertIsNone(subtask_task.epic_key)  # Should be None as it has a parent
        self.assertEqual(subtask_task.parent_key, 'STORY-1')

    @patch('mlx.jira_juggler.jira_juggler.JIRA', autospec=True)
    def test_hierarchical_task_building(self, jira_mock):
        """Test building of hierarchical task structures"""
        # Create mock issues
        epic_issue = self._mock_jira_issue('EPIC-1', 'Test Epic', 'testuser', [5 * self.SECS_PER_DAY, None, None],
                                           issue_type='Epic')
        story1_issue = self._mock_jira_issue('STORY-1', 'Story 1', 'testuser', [2 * self.SECS_PER_DAY, None, None],
                                             epic_key='EPIC-1', issue_type='Story')
        story2_issue = self._mock_jira_issue('STORY-2', 'Story 2', 'testuser', [3 * self.SECS_PER_DAY, None, None],
                                             epic_key='EPIC-1', issue_type='Story')
        subtask_issue = self._mock_jira_issue('SUB-1', 'Subtask 1', 'testuser', [1 * self.SECS_PER_DAY, None, None],
                                              parent_key='STORY-1', issue_type='Sub-task')

        jirahandle = jira_mock.return_value
        jirahandle.enhanced_search_issues.return_value = [epic_issue, story1_issue, story2_issue, subtask_issue]
        jirahandle.issue_link_types.return_value = ISSUE_LINK_TYPES

        juggler = dut.JiraJuggler(self.URL, self.USER, self.PASSWD, self.QUERY)
        tasks = juggler.load_issues_from_jira(enable_epics=True)

        # Should return only top-level tasks (epic in this case)
        self.assertEqual(len(tasks), 1)
        epic_task = tasks[0]

        # Verify epic has children
        self.assertEqual(epic_task.key, 'EPIC-1')
        self.assertEqual(len(epic_task.children), 2)  # Two stories

        # Verify story children
        story_keys = [child.key for child in epic_task.children]
        self.assertIn('STORY-1', story_keys)
        self.assertIn('STORY-2', story_keys)

        # Verify story has subtask
        story1_task = next(child for child in epic_task.children if child.key == 'STORY-1')
        self.assertEqual(len(story1_task.children), 1)
        self.assertEqual(story1_task.children[0].key, 'SUB-1')

    @patch('mlx.jira_juggler.jira_juggler.JIRA', autospec=True)
    def test_effort_rollup_calculation(self, jira_mock):
        """Test effort rollup from children to parents"""
        # Create hierarchy with known effort values
        epic_issue = self._mock_jira_issue('EPIC-1', 'Test Epic', 'testuser', [0, None, None],
                                           issue_type='Epic')  # Epic has no effort initially
        story_issue = self._mock_jira_issue('STORY-1', 'Story 1', 'testuser', [2 * self.SECS_PER_DAY, None, None],
                                            epic_key='EPIC-1', issue_type='Story')
        subtask1_issue = self._mock_jira_issue('SUB-1', 'Subtask 1', 'testuser', [1 * self.SECS_PER_DAY, None, None],
                                               parent_key='STORY-1', issue_type='Sub-task')
        subtask2_issue = self._mock_jira_issue('SUB-2', 'Subtask 2', 'testuser', [0.5 * self.SECS_PER_DAY, None, None],
                                               parent_key='STORY-1', issue_type='Sub-task')

        jirahandle = jira_mock.return_value
        jirahandle.enhanced_search_issues.return_value = [epic_issue, story_issue, subtask1_issue, subtask2_issue]
        jirahandle.issue_link_types.return_value = ISSUE_LINK_TYPES

        juggler = dut.JiraJuggler(self.URL, self.USER, self.PASSWD, self.QUERY)
        tasks = juggler.load_issues_from_jira(enable_epics=True)

        epic_task = tasks[0]
        story_task = epic_task.children[0]

        # Container tasks no longer carry an effort property; verify roll-up via calculation
        self.assertIsNone(epic_task.properties['effort'].value)
        self.assertIsNone(story_task.properties['effort'].value)

        # Epic effort should be sum of all descendants (1 + 0.5 = 1.5 days, since story is a container)
        self.assertAlmostEqual(epic_task.calculate_rolled_up_effort(), 1.5, places=2)

        # Story effort should be sum of its subtasks (1 + 0.5 = 1.5 days)
        self.assertAlmostEqual(story_task.calculate_rolled_up_effort(), 1.5, places=2)

    @patch('mlx.jira_juggler.jira_juggler.JIRA', autospec=True)
    def test_nested_taskjuggler_output(self, jira_mock):
        """Test nested TaskJuggler output format"""
        epic_issue = self._mock_jira_issue('EPIC-1', 'Test Epic', 'testuser', [0, None, None],
                                           issue_type='Epic')
        story_issue = self._mock_jira_issue('STORY-1', 'Story 1', 'testuser', [1 * self.SECS_PER_DAY, None, None],
                                            epic_key='EPIC-1', issue_type='Story')

        jirahandle = jira_mock.return_value
        jirahandle.enhanced_search_issues.return_value = [epic_issue, story_issue]
        jirahandle.issue_link_types.return_value = ISSUE_LINK_TYPES

        juggler = dut.JiraJuggler(self.URL, self.USER, self.PASSWD, self.QUERY)
        tasks = juggler.load_issues_from_jira(enable_epics=True)

        epic_task = tasks[0]
        output = str(epic_task)

        # Verify nested structure in output
        self.assertIn('task EPIC_1 "Test Epic"', output)
        self.assertIn('    task STORY_1 "Story 1"', output)  # Indented child
        self.assertIn('Jira "EPIC-1"', output)
        self.assertIn('Jira "STORY-1"', output)

    @patch('mlx.jira_juggler.jira_juggler.JIRA', autospec=True)
    def test_mixed_hierarchy_and_flat_tasks(self, jira_mock):
        """Test handling of mixed hierarchical and flat task structures"""
        # Mix of epic with children and standalone tasks
        epic_issue = self._mock_jira_issue('EPIC-1', 'Test Epic', 'testuser', [0, None, None],
                                           issue_type='Epic')
        story_issue = self._mock_jira_issue('STORY-1', 'Story in Epic', 'testuser', [1 * self.SECS_PER_DAY, None, None],
                                            epic_key='EPIC-1', issue_type='Story')
        standalone_issue = self._mock_jira_issue('TASK-1', 'Standalone Task', 'testuser', [2 * self.SECS_PER_DAY, None, None],
                                                 issue_type='Task')

        jirahandle = jira_mock.return_value
        jirahandle.enhanced_search_issues.return_value = [epic_issue, story_issue, standalone_issue]
        jirahandle.issue_link_types.return_value = ISSUE_LINK_TYPES

        juggler = dut.JiraJuggler(self.URL, self.USER, self.PASSWD, self.QUERY)
        tasks = juggler.load_issues_from_jira(enable_epics=True)

        # Should return 2 top-level tasks: epic and standalone
        self.assertEqual(len(tasks), 2)

        task_keys = [task.key for task in tasks]
        self.assertIn('EPIC-1', task_keys)
        self.assertIn('TASK-1', task_keys)

        # Epic should have child, standalone should not
        epic_task = next(task for task in tasks if task.key == 'EPIC-1')
        standalone_task = next(task for task in tasks if task.key == 'TASK-1')

        self.assertEqual(len(epic_task.children), 1)
        self.assertEqual(len(standalone_task.children), 0)

    @patch('mlx.jira_juggler.jira_juggler.JIRA', autospec=True)
    def test_epic_disabled_flat_output(self, jira_mock):
        """Test that epic relationships are ignored when enable_epics=False"""
        epic_issue = self._mock_jira_issue('EPIC-1', 'Test Epic', 'testuser', [3 * self.SECS_PER_DAY, None, None],
                                           issue_type='Epic')
        story_issue = self._mock_jira_issue('STORY-1', 'Story 1', 'testuser', [1 * self.SECS_PER_DAY, None, None],
                                            epic_key='EPIC-1', issue_type='Story')

        jirahandle = jira_mock.return_value
        jirahandle.enhanced_search_issues.return_value = [epic_issue, story_issue]
        jirahandle.issue_link_types.return_value = ISSUE_LINK_TYPES

        juggler = dut.JiraJuggler(self.URL, self.USER, self.PASSWD, self.QUERY)
        tasks = juggler.load_issues_from_jira(enable_epics=False)  # Disabled

        # Should return all tasks as flat list (no hierarchy)
        self.assertEqual(len(tasks), 2)

        # No children should be assigned
        for task in tasks:
            self.assertEqual(len(task.children), 0)

    @patch('mlx.jira_juggler.jira_juggler.JIRA', autospec=True)
    def test_orphaned_children_handling(self, jira_mock):
        """Test handling of child issues where parent/epic is not in the query results"""
        # Story references epic that's not in results
        story_issue = self._mock_jira_issue('STORY-1', 'Orphaned Story', 'testuser', [1 * self.SECS_PER_DAY, None, None],
                                            epic_key='EPIC-99', issue_type='Story')
        # Subtask references parent that's not in results
        subtask_issue = self._mock_jira_issue('SUB-1', 'Orphaned Subtask', 'testuser', [0.5 * self.SECS_PER_DAY, None, None],
                                              parent_key='STORY-99', issue_type='Sub-task')

        jirahandle = jira_mock.return_value
        jirahandle.enhanced_search_issues.return_value = [story_issue, subtask_issue]
        jirahandle.issue_link_types.return_value = ISSUE_LINK_TYPES

        juggler = dut.JiraJuggler(self.URL, self.USER, self.PASSWD, self.QUERY)
        tasks = juggler.load_issues_from_jira(enable_epics=True)

        # Both orphaned issues should be returned as top-level tasks
        self.assertEqual(len(tasks), 2)

        task_keys = [task.key for task in tasks]
        self.assertIn('STORY-1', task_keys)
        self.assertIn('SUB-1', task_keys)

        # Neither should have children
        for task in tasks:
            self.assertEqual(len(task.children), 0)

    @patch('mlx.jira_juggler.jira_juggler.JIRA', autospec=True)
    def test_epic_field_variations(self, jira_mock):
        """Test detection of epic links through various field names"""
        # Create stories with different epic field patterns
        story_epic_field = self._mock_jira_issue('STORY-1', 'Story with epic field', 'testuser',
                                                 [1 * self.SECS_PER_DAY], epic_key='EPIC-1', issue_type='Story')
        epic_issue = self._mock_jira_issue('EPIC-1', 'Test Epic', 'testuser', [0, None, None], issue_type='Epic')

        jirahandle = jira_mock.return_value
        jirahandle.enhanced_search_issues.return_value = [epic_issue, story_epic_field]
        jirahandle.issue_link_types.return_value = ISSUE_LINK_TYPES

        juggler = dut.JiraJuggler(self.URL, self.USER, self.PASSWD, self.QUERY)
        tasks = juggler.load_issues_from_jira(enable_epics=True)

        # Should detect the epic relationship
        self.assertEqual(len(tasks), 1)  # Only epic as top-level
        epic_task = tasks[0]
        self.assertEqual(len(epic_task.children), 1)
        self.assertEqual(epic_task.children[0].key, 'STORY-1')

    @patch('mlx.jira_juggler.jira_juggler.JIRA', autospec=True)
    def test_epic_hierarchy_file_output(self, jira_mock):
        """Test that epic hierarchy generates correct TaskJuggler file output"""
        import tempfile
        import os

        # Create comprehensive hierarchy: Epic -> Story -> Subtask
        epic_issue = self._mock_jira_issue('EPIC-1', 'User Management Epic', 'john', [0, None, None],
                                           issue_type='Epic')
        story_issue = self._mock_jira_issue('STORY-1', 'User Authentication Story', 'john', [2 * self.SECS_PER_DAY, None, None],
                                            epic_key='EPIC-1', issue_type='Story')
        subtask1_issue = self._mock_jira_issue('SUB-1', 'Login UI Subtask', 'jane', [1 * self.SECS_PER_DAY, None, None],
                                               parent_key='STORY-1', issue_type='Sub-task')
        subtask2_issue = self._mock_jira_issue('SUB-2', 'Authentication Logic', 'john', [1 * self.SECS_PER_DAY, None, None],
                                               parent_key='STORY-1', issue_type='Sub-task')

        jirahandle = jira_mock.return_value
        jirahandle.enhanced_search_issues.return_value = [epic_issue, story_issue, subtask1_issue, subtask2_issue]
        jirahandle.issue_link_types.return_value = ISSUE_LINK_TYPES

        juggler = dut.JiraJuggler(self.URL, self.USER, self.PASSWD, self.QUERY)

        # Generate file with epic hierarchy enabled
        with tempfile.NamedTemporaryFile(mode='w', suffix='.tjp', delete=False) as temp_file:
            temp_filename = temp_file.name

        try:
            # Generate the file
            juggler.juggle(output=temp_filename, enable_epics=True)

            # Read the generated file
            with open(temp_filename, 'r') as f:
                generated_output = f.read()

            # Expected hierarchical structure
            expected_patterns = [
                'task EPIC_1 "User Management Epic"',  # Epic task
                'Jira "EPIC-1"',  # Epic Jira reference
                '    task STORY_1 "User Authentication Story"',  # Indented story
                'Jira "STORY-1"',  # Story Jira reference
                '        task SUB_1 "Login UI Subtask"',  # Double-indented subtask
                'Jira "SUB-1"',  # Subtask 1 Jira reference
                '        task SUB_2 "Authentication Logic"',  # Double-indented subtask
                'Jira "SUB-2"',  # Subtask 2 Jira reference
                'allocate john',  # John's allocation
                'allocate jane',  # Jane's allocation
                'effort 1.0d'  # Effort on subtasks
            ]

            # Verify all expected patterns are in the output
            for pattern in expected_patterns:
                self.assertIn(
                    pattern,
                    generated_output,
                    f"Expected pattern '{pattern}' not found in generated output",
                )

            # Verify the structure is properly nested (check indentation)
            lines = generated_output.split('\n')
            epic_found = False
            story_found = False
            for i, line in enumerate(lines):
                if 'task EPIC_1' in line:
                    epic_found = True
                elif epic_found and 'task STORY_1' in line:
                    # Story should be indented under epic
                    self.assertTrue(
                        line.startswith('    '),
                        "Story task should be indented under epic",
                    )
                    story_found = True
                elif story_found and 'task SUB_1' in line:
                    # Subtask should be double-indented
                    self.assertTrue(
                        line.startswith('        '),
                        "Subtask should be double-indented under story",
                    )

        finally:
            # Cleanup
            if os.path.exists(temp_filename):
                os.unlink(temp_filename)

    @patch('mlx.jira_juggler.jira_juggler.JIRA', autospec=True)
    def test_flat_vs_hierarchical_file_comparison(self, jira_mock):
        """Test comparing flat output vs hierarchical output in generated files"""
        import tempfile
        import os

        # Create the same issues
        epic_issue = self._mock_jira_issue('EPIC-1', 'Test Epic', 'dev1', [1 * self.SECS_PER_DAY, None, None], issue_type='Epic')
        story_issue = self._mock_jira_issue('STORY-1', 'Test Story', 'dev1', [1 * self.SECS_PER_DAY, None, None],
                                            epic_key='EPIC-1', issue_type='Story')

        jirahandle = jira_mock.return_value
        jirahandle.enhanced_search_issues.return_value = [epic_issue, story_issue]
        jirahandle.issue_link_types.return_value = ISSUE_LINK_TYPES

        juggler = dut.JiraJuggler(self.URL, self.USER, self.PASSWD, self.QUERY)

        flat_file = None
        hierarchical_file = None

        try:
            # Generate flat output (epic support disabled)
            with tempfile.NamedTemporaryFile(mode='w', suffix='_flat.tjp', delete=False) as temp_file:
                flat_file = temp_file.name
            juggler.juggle(output=flat_file, enable_epics=False)

            # Generate hierarchical output (epic support enabled)
            with tempfile.NamedTemporaryFile(mode='w', suffix='_hierarchical.tjp', delete=False) as temp_file:
                hierarchical_file = temp_file.name
            juggler.juggle(output=hierarchical_file, enable_epics=True)

            # Read both files
            with open(flat_file, 'r') as f:
                flat_content = f.read()
            with open(hierarchical_file, 'r') as f:
                hierarchical_content = f.read()

            # Flat output should have both tasks at root level
            flat_lines = [line.strip() for line in flat_content.split('\n') if line.strip()]
            epic_tasks_in_flat = [line for line in flat_lines if line.startswith('task ')]
            self.assertEqual(len(epic_tasks_in_flat), 2, "Flat output should have 2 separate tasks")

            # Hierarchical output should have nested structure
            hierarchical_lines = hierarchical_content.split('\n')
            root_tasks = [line for line in hierarchical_lines if line.startswith('task ')]
            nested_tasks = [line for line in hierarchical_lines if line.startswith('    task ')]

            self.assertEqual(len(root_tasks), 1, "Hierarchical output should have 1 root task (epic)")
            self.assertEqual(len(nested_tasks), 1, "Hierarchical output should have 1 nested task (story)")

            # Verify the nested task is the story, not the epic
            self.assertIn('STORY_1', nested_tasks[0], "Nested task should be the story")
            self.assertIn('EPIC_1', root_tasks[0], "Root task should be the epic")

        finally:
            # Cleanup
            for filename in [flat_file, hierarchical_file]:
                if filename and os.path.exists(filename):
                    os.unlink(filename)

    @patch('mlx.jira_juggler.jira_juggler.JIRA', autospec=True)
    def test_complex_hierarchy_file_output(self, jira_mock):
        """Test complex hierarchy with multiple epics and mixed relationships"""
        import tempfile
        import os

        # Create complex scenario: 2 epics, mixed relationships
        epic1_issue = self._mock_jira_issue('EPIC-1', 'Frontend Epic', 'team1', [0, None, None], issue_type='Epic')
        epic2_issue = self._mock_jira_issue('EPIC-2', 'Backend Epic', 'team2', [0, None, None], issue_type='Epic')

        story1_issue = self._mock_jira_issue('STORY-1', 'UI Components', 'dev1', [3 * self.SECS_PER_DAY, None, None],
                                             epic_key='EPIC-1', issue_type='Story')
        story2_issue = self._mock_jira_issue('STORY-2', 'API Endpoints', 'dev2', [2 * self.SECS_PER_DAY, None, None],
                                             epic_key='EPIC-2', issue_type='Story')

        # Standalone task (no epic)
        standalone_issue = self._mock_jira_issue('TASK-1', 'Documentation Update', 'writer', [1 * self.SECS_PER_DAY, None, None],
                                                 issue_type='Task')

        # Subtasks for first story
        sub1_issue = self._mock_jira_issue('SUB-1', 'Button Component', 'dev1', [1 * self.SECS_PER_DAY, None, None],
                                           parent_key='STORY-1', issue_type='Sub-task')
        sub2_issue = self._mock_jira_issue('SUB-2', 'Form Component', 'dev1', [2 * self.SECS_PER_DAY, None, None],
                                           parent_key='STORY-1', issue_type='Sub-task')

        jirahandle = jira_mock.return_value
        jirahandle.enhanced_search_issues.return_value = [
            epic1_issue,
            epic2_issue,
            story1_issue,
            story2_issue,
            standalone_issue,
            sub1_issue,
            sub2_issue,
        ]
        jirahandle.issue_link_types.return_value = ISSUE_LINK_TYPES

        juggler = dut.JiraJuggler(self.URL, self.USER, self.PASSWD, self.QUERY)

        with tempfile.NamedTemporaryFile(mode='w', suffix='.tjp', delete=False) as temp_file:
            temp_filename = temp_file.name

        try:
            # Generate hierarchical output
            juggler.juggle(output=temp_filename, enable_epics=True)

            with open(temp_filename, 'r') as f:
                content = f.read()

            # Should have 3 top-level tasks: 2 epics + 1 standalone
            root_tasks = [line for line in content.split('\n') if line.startswith('task ')]
            self.assertEqual(len(root_tasks), 3, "Should have 3 top-level tasks")

            # Verify epic structure
            self.assertIn('task EPIC_1 "Frontend Epic"', content)
            self.assertIn('task EPIC_2 "Backend Epic"', content)
            self.assertIn('task TASK_1 "Documentation Update"', content)

            # Verify nested stories under epics
            self.assertIn('    task STORY_1 "UI Components"', content)
            self.assertIn('    task STORY_2 "API Endpoints"', content)

            # Verify subtasks under story
            self.assertIn('        task SUB_1 "Button Component"', content)
            self.assertIn('        task SUB_2 "Form Component"', content)

            # Verify effort rollup (story should have 1+2=3 days from subtasks)
            lines = content.split('\n')
            in_story1 = False
            for line in lines:
                if 'task STORY_1' in line:
                    in_story1 = True
                elif in_story1 and 'effort 3.0d' in line:
                    # Found the rolled up effort
                    break
                elif line.startswith('task ') and in_story1:
                    # Moved to next task without finding effort
                    in_story1 = False
            else:
                if in_story1:
                    self.fail("Expected effort 3.0d for STORY-1 with rolled up subtask effort")

        finally:
            if os.path.exists(temp_filename):
                os.unlink(temp_filename)

    def test_epic_output_format_validation(self):
        """Test that epic output follows correct TaskJuggler syntax"""
        # Create a simple epic with child for format validation
        epic_task = dut.JugglerTask()
        epic_task.key = 'EPIC-1'
        epic_task.summary = 'Test Epic'
        epic_task.is_epic = True
        epic_task.properties['allocate'] = dut.JugglerTaskAllocate()
        epic_task.properties['allocate'].value = 'testuser'
        epic_task.properties['effort'] = dut.JugglerTaskEffort()
        epic_task.properties['effort'].value = None  # container has no own effort
        epic_task.properties['depends'] = dut.JugglerTaskDepends()
        epic_task.properties['time'] = dut.JugglerTaskTime()

        story_task = dut.JugglerTask()
        story_task.key = 'STORY-1'
        story_task.summary = 'Test Story'
        story_task.properties['allocate'] = dut.JugglerTaskAllocate()
        story_task.properties['allocate'].value = 'developer'
        story_task.properties['effort'] = dut.JugglerTaskEffort()
        story_task.properties['effort'].value = 1.0
        story_task.properties['depends'] = dut.JugglerTaskDepends()
        story_task.properties['time'] = dut.JugglerTaskTime()

        epic_task.add_child(story_task)

        output = str(epic_task)

        # Validate TaskJuggler syntax elements
        syntax_checks = [
            ('Opening brace', 'task EPIC_1 "Test Epic" {'),
            ('Jira reference', 'Jira "EPIC-1"'),
            ('Allocate property', 'allocate testuser'),
            # No explicit effort on container
            ('Nested task', '    task STORY_1 "Test Story" {'),
            ('Nested Jira ref', 'Jira "STORY-1"'),
            ('Nested allocate', 'allocate developer'),
            ('Closing braces', output.count('{') == output.count('}'))
        ]

        for check_name, check_condition in syntax_checks:
            if isinstance(check_condition, str):
                self.assertIn(check_condition, output, f"Missing {check_name}")
            else:
                self.assertTrue(check_condition, f"Failed {check_name}")

        # Verify proper indentation
        lines = output.split('\n')
        for line in lines:
            if 'task STORY_1' in line:
                self.assertTrue(line.startswith('    '), "Child task should be indented with 4 spaces")
            elif 'allocate developer' in line:
                self.assertTrue(line.startswith('        '), "Child properties should be double-indented")

        # Verify no malformed brackets or quotes
        self.assertEqual(output.count('"') % 2, 0, "Quotes should be balanced")
        self.assertEqual(output.count('{'), output.count('}'), "Braces should be balanced")
