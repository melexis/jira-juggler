#!/usr/bin/python
# -*- coding: utf-8 -*-

# python -m unittest discover -s scripts/ -p '*_test.py'

import unittest

try:
    from unittest.mock import MagicMock, patch
except ImportError as err:
    print("unittest.mock import failed")
    try:
        from mock import MagicMock, patch
    except ImportError as err:
        print("mock import failed. installing mock")
        import pip
        pip.main(['install', 'mock'])
        from mock import MagicMock, patch

from jira import JIRA, JIRAError
from jira_juggler import jira_juggler

class TestJiraJuggler(unittest.TestCase):
    '''Testing JiraJuggler interface'''

    def SetUp(self):
        '''SetUp is run before each test to provide clean working environment'''

    @patch('jira_juggler.jira_juggler.JIRA', autospec=True)
    def test_empty_query_result(self, jira_mock):
        '''Test for Jira not returning any task on the given query'''

        url = 'http://my-non-existing-jira.melexis.com'
        user = 'justme'
        passwd = 'myuselesspassword'
        q = 'some random query'
        jira_mock.return_value = MagicMock(spec=JIRA)
        juggler = jira_juggler.JiraJuggler(url, user, passwd, q)
        self.assertEqual(q, juggler.query)

        jira_mock.return_value.search_issues.return_value = []
        juggler.juggle()
        jira_mock.return_value.search_issues.assert_called_once_with(q, maxResults=jira_juggler.JIRA_PAGE_SIZE, startAt=0)

if __name__ == '__main__':
    unittest.main()
