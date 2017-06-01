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

try:
    from jira import JIRA, JIRAError
except ImportError as err:
    print("jira import failed")
    import pip
    pip.main(['install', 'jira'])
    from jira import JIRA, JIRAError

from jira_juggler import jira_juggler as dut

class TestJiraJuggler(unittest.TestCase):
    '''Testing JiraJuggler interface'''

    URL = 'http://my-non-existing-jira.melexis.com'
    USER = 'justme'
    PASSWD = 'myuselesspassword'
    QUERY = 'some random query'

    def SetUp(self):
        '''SetUp is run before each test to provide clean working environment'''

    @patch('jira_juggler.jira_juggler.JIRA', autospec=True)
    def test_empty_query_result(self, jira_mock):
        '''Test for Jira not returning any task on the given query'''
        jira_mock_object = MagicMock(spec=JIRA)
        jira_mock.return_value = jira_mock_object
        juggler = dut.JiraJuggler(self.URL, self.USER, self.PASSWD, self.QUERY)
        self.assertEqual(self.QUERY, juggler.query)

        jira_mock_object.search_issues.return_value = []
        juggler.juggle()
        jira_mock_object.search_issues.assert_called_once_with(self.QUERY, maxResults=dut.JIRA_PAGE_SIZE, startAt=0)

if __name__ == '__main__':
    unittest.main()
