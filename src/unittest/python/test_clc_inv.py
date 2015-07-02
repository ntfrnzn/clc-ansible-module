#!/usr/bin/python

import clc_inv as clc_inv
import clc as clc_sdk
from clc import CLCException
import mock
from mock import patch
from mock import create_autospec
import unittest

class TestClcInvFunctions(unittest.TestCase):

    def setUp(self):
        self.clc = mock.MagicMock()
        self.module = mock.MagicMock()
        self.datacenter=mock.MagicMock()

    @patch('clc_inv.clc')
    def test_find_hostvars_single_server_none(self, mock_clc_sdk):
        server = mock.MagicMock()
        server.name = 'testServerWithNoDetails'
        server.data = {}
        mock_clc_sdk.v2.Server.return_value = server
        result = clc_inv._find_hostvars_single_server('testServerWithNoDetails')
        self.assertIsNone(result)

    @patch('clc_inv.clc')
    def test_find_hostvars_single_server(self, mock_clc_sdk):
        server = mock.MagicMock()
        server.name = 'testServerWithNoDetails'
        server.data = {'details':
                           {'ipAddresses':
                                [
                                    {'internal':'true'}
                                ]
                           }
                        }
        mock_clc_sdk.v2.Server.return_value = server
        result = clc_inv._find_hostvars_single_server('testServerWithNoDetails')
        self.assertIsNone(result)

    @patch.object(clc_inv, 'clc')
    def test_set_clc_credentials_from_env(self, mock_clc_sdk):
        with patch.dict('os.environ', {'CLC_V2_API_TOKEN': 'dummyToken',
                                       'CLC_ACCT_ALIAS': 'TEST'}):
            clc_inv._set_clc_credentials_from_env()
        self.assertEqual(clc_inv.clc._LOGIN_TOKEN_V2, 'dummyToken')
        self.assertFalse(mock_clc_sdk.v2.SetCredentials.called)
        self.assertEqual(self.module.fail_json.called, False)

    def test_is_list_flat(self):
        list = [1,2,3]
        res = clc_inv._is_list_flat(list)
        self.assertEqual(res, True)

    def test_flatten_list(self):
        list = [1,2,3]
        res = clc_inv._flatten_list(list)
        self.assertEqual(res, [1,2,3])

    @patch('clc_inv._find_all_groups')
    @patch('clc_inv._get_servers_from_groups')
    @patch('clc_inv._find_all_hostvars_for_servers')
    @patch('clc_inv._build_hostvars_dynamic_groups')
    @patch('clc_inv._set_clc_credentials_from_env')
    def test_print_inventory_json(self, mock_creds, mock_hostvars_d, mock_hostvars, mock_servers, mock_groups):
        try:
            mock_groups.return_value = {'groups':['group1', 'group2']}
            mock_servers.return_value = ['server1', 'server2']
            mock_hostvars.return_value = ['var1', 'var2']
            mock_hostvars_d.return_value = {'dgroups':['dg1', 'dg2']}
            clc_inv.print_inventory_json()
        except:
            self.fail('Exception was thrown when it was not expected')

if __name__ == '__main__':
    unittest.main()
