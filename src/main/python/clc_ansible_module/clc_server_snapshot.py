#!/usr/bin/python

DOCUMENTATION = '''
module: clc_server
short_desciption: Create, Delete and Restore server snapshots in CenturyLink Cloud.
description:
  - An Ansible module to Create, Delete and Restore server snapshots in CenturyLink Cloud.
options:
  server_ids:
    description:
      - A list of server Ids to snapshot.
    default: []
    required: True
    aliases: []
  expiration_days:
    description:
      - The number of days to keep the server snapshot before it expires.
    default: 7
    required: False
    aliases: []
  state:
    description:
      - The state to insure that the provided resources are in.
    default: 'present'
    required: False
    choices: ['present', 'absent', 'restore']
    aliases: []
  wait:
    description:
      - Whether to wait for the provisioning tasks to finish before returning.
    default: True
    required: False
    choices: [ True, False]
    aliases: []
'''

EXAMPLES = '''
# Note - You must set the CLC_V2_API_USERNAME And CLC_V2_API_PASSWD Environment variables before running these examples

- name: Create server snapshot
  clc_server_snapshot:
    server_ids:
        - UC1WFSDTEST01
        - UC1WFSDTEST02
    expiration_days: 10
    wait: True
    state: present

- name: Restore server snapshot
  clc_server_snapshot:
    server_ids:
        - UC1WFSDTEST01
        - UC1WFSDTEST02
    wait: True
    state: restore

- name: Delete server snapshot
  clc_server_snapshot:
    server_ids:
        - UC1WFSDTEST01
        - UC1WFSDTEST02
    wait: True
    state: absent
'''

import json
import socket
import time
from ansible.module_utils.basic import *
#
#  Requires the clc-python-sdk.
#  sudo pip install clc-sdk
#
try:
    import clc as clc_sdk
    from clc import CLCException
except ImportError:
    clc_found = False
    clc_sdk = None
else:
    CLC_FOUND = True

class ClcSnapshot():

    clc = clc_sdk
    module = None

    STATSD_HOST = '64.94.114.218'
    STATSD_PORT = 2003
    STATS_SNAPSHOT_CREATE = 'stats_counts.wfaas.clc.ansible.snapshot.create'
    STATS_SNAPSHOT_DELETE = 'stats_counts.wfaas.clc.ansible.snapshot.delete'
    STATS_SNAPSHOT_RESTORE = 'stats_counts.wfaas.clc.ansible.snapshot.restore'
    SOCKET_CONNECTION_TIMEOUT = 3

    def __init__(self, module):
        self.module = module
        if not CLC_FOUND:
            self.module.fail_json(
                msg='clc-python-sdk required for this module')

    def process_request(self):
        """
        Process the request - Main Code Path
        :return: Returns with either an exit_json or fail_json
        """
        p = self.module.params

        if not CLC_FOUND:
            self.module.fail_json(msg='clc-python-sdk required for this module')

        server_ids = p['server_ids']
        expiration_days = p['expiration_days']
        wait = p['wait']
        state = p['state']
        command_list = []

        if not server_ids:
            return self.module.fail_json(msg='List of Server ids are required')

        self._set_clc_creds_from_env()
        if state == 'present':
            command_list.append(
                lambda: self.clc_create_servers_snapshot(
                    server_ids=server_ids,
                    expiration_days=expiration_days))
        elif state == 'absent':
            command_list.append(
                lambda: self.clc_delete_servers_snapshot(
                    server_ids=server_ids))
        elif state == 'restore':
            command_list.append(
                lambda: self.clc_restore_servers_snapshot(
                    server_ids=server_ids))
        else:
            return self.module.fail_json(msg="Unknown State: " + state)

        has_made_changes, result_servers = self.run_clc_commands(
            command_list)
        return self.module.exit_json(
            changed=has_made_changes,
            servers=result_servers)

    def run_clc_commands(self, command_list):
        """
        Executes the CLC commands
        :param command_list: the list of commands to be executed
        :return: a flag indicating if any change made to the server and the list of servers modified
        """
        requests_list = []
        changed_servers = []
        for command in command_list:
            requests, servers = command()
            requests_list += requests
            changed_servers += servers
        self._wait_for_requests_to_complete(requests_list)
        has_made_changes, result_changed_servers = self._parse_server_results(
            changed_servers)
        return has_made_changes, result_changed_servers

    def _wait_for_requests_to_complete(self, requests_lst, action='create'):
        for request in requests_lst:
            request.WaitUntilComplete()
            for request_details in request.requests:
                if request_details.Status() != 'succeeded':
                    self.module.fail_json(
                        msg='Unable to ' +
                        action +
                        ' Public IP for ' +
                        request.server.id +
                        ': ' +
                        request.Status())

    @staticmethod
    def _parse_server_results(servers):
        servers_result = []
        changed = False
        snapshot = ''
        for server in servers:
            has_snapshot = len(server.GetSnapshots()) > 0
            if has_snapshot:
                changed = True
                snapshot = str(server.GetSnapshots()[0])
            ipaddress = server.data['details']['ipAddresses'][0]['internal']
            server.data['ipaddress'] = ipaddress
            server.data['snapshot'] = snapshot
            servers_result.append(ipaddress)
        return changed, servers_result

    @staticmethod
    def define_argument_spec():
        """
        This function defnines the dictionary object required for
        package module
        :return: the package dictionary object
        """
        argument_spec = dict(
            server_ids=dict(type='list', required=True),
            expiration_days=dict(default=7),
            wait=dict(default=True),
            state=dict(default='present', choices=['present', 'absent', 'restore']),
        )
        return argument_spec

    def clc_create_servers_snapshot(self, server_ids, expiration_days):
        """
        Create the snapshot on the given list of CLC servers
        :param server_ids: the list of clc servier ids to create snapshot
        :param expiration_days: the number of days to keep the snapshot
        :return: the create snapshot API response and the list of servers modified
        """
        try:
            servers = self._get_servers_from_clc(
            server_ids,
            'Failed to obtain server list from the CLC API')
            if not servers:
                return self.module.fail_json(msg='Failed to create snap shot as there are no servers available')
            servers_to_change = [
                server for server in servers if len(
                    server.GetSnapshots()) == 0]
            ClcSnapshot._push_metric(ClcSnapshot.STATS_SNAPSHOT_CREATE, len(servers_to_change))
            return [server.CreateSnapshot(delete_existing=True, expiration_days=expiration_days)
                    for server in servers_to_change], servers_to_change
        except CLCException as ex:
            return self.module.fail_json(msg='Failed to create snap shot with Error : %s' %(ex))


    def clc_delete_servers_snapshot(self, server_ids):
        """
        deletes the existing servers snapshot
        :param server_ids: the list of clc server ids
        :return: the delete snapshot API response and the list of servers modified
        """
        servers = self._get_servers_from_clc(
            server_ids,
            'Failed to obtain server list from the CLC API')
        if not servers:
                return self.module.fail_json(msg='Failed to create snap shot as there are no servers available')
        servers_to_change = [
            server for server in servers if len(
                server.GetSnapshots()) == 1]
        ClcSnapshot._push_metric(ClcSnapshot.STATS_SNAPSHOT_DELETE, len(servers_to_change))
        return [server.DeleteSnapshot()
                for server in servers_to_change], servers_to_change

    def clc_restore_servers_snapshot(self, server_ids):
        '''
        restores to the existing snapshot (if available)
        :param server_ids: the list of target clc server ids
        :return: the restore snapshot API response and the list of servers modified
        '''
        servers = self._get_servers_from_clc(
            server_ids,
            'Failed to obtain server list from the CLC API')
        if not servers:
                return self.module.fail_json(msg='Failed to create snap shot as there are no servers available')
        servers_to_change = [
            server for server in servers if len(
                server.GetSnapshots()) == 1]
        ClcSnapshot._push_metric(ClcSnapshot.STATS_SNAPSHOT_RESTORE, len(servers_to_change))
        return [server.RestoreSnapshot()
                for server in servers_to_change], servers_to_change


    def _get_servers_from_clc(self, server_list, message):
        """
        Internal function to fetch list of CLC server objects from a list of server ids
        :param the list server ids
        :return the list of CLC server objects
        """
        try:
            return self.clc.v2.Servers(server_list).servers
        except CLCException as ex:
            self.module.fail_json(msg=message + ': %s' %ex)

    def _set_clc_creds_from_env(self):
        """
        Internal function to set the CLC credentials
        """
        env = os.environ
        v2_api_token = env.get('CLC_V2_API_TOKEN', False)
        v2_api_username = env.get('CLC_V2_API_USERNAME', False)
        v2_api_passwd = env.get('CLC_V2_API_PASSWD', False)
        clc_alias = env.get('CLC_ACCT_ALIAS', False)

        if v2_api_token and clc_alias:
            self.clc._LOGIN_TOKEN_V2 = v2_api_token
            self.clc._V2_ENABLED = True
            self.clc.ALIAS = clc_alias
        elif v2_api_username and v2_api_passwd:
            self.clc.v2.SetCredentials(
                api_username=v2_api_username,
                api_passwd=v2_api_passwd)
        else:
            return self.module.fail_json(
                msg="You must set the CLC_V2_API_USERNAME and CLC_V2_API_PASSWD "
                    "environment variables")
        return self

    @staticmethod
    def _push_metric(path, count):
        try:
            sock = socket.socket()
            sock.settimeout(ClcSnapshot.SOCKET_CONNECTION_TIMEOUT)
            sock.connect((ClcSnapshot.STATSD_HOST, ClcSnapshot.STATSD_PORT))
            sock.sendall('%s %s %d\n' %(path, count, int(time.time())))
            sock.close()
        except socket.gaierror:
            # do nothing, ignore and move forward
            error = ''
        except socket.error:
            #nothing, ignore and move forward
            error = ''


def main():
    """
    Main function
    :return: None
    """
    module = AnsibleModule(
            argument_spec=ClcSnapshot.define_argument_spec()
        )
    clc_snapshot = ClcSnapshot(module)
    clc_snapshot.process_request()


if __name__ == '__main__':
    main()