#!/usr/bin/python
#
# Copyright 2016 F5 Networks Inc.
#
# This file is part of Ansible
#
# Ansible is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Ansible is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Ansible.  If not, see <http://www.gnu.org/licenses/>.

ANSIBLE_METADATA = {'status': ['preview'],
                    'supported_by': 'community',
                    'version': '1.0'}

DOCUMENTATION = '''
module: iworkflow_license_pool_member
short_description: Manages members in a license pool.
description:
  - Manages members in a license pool. By adding and removing members from
    a pool, you will implicitly be licensing and unlicensing them.
version_added: 2.3
options:
  device:
    description:
      - Hostname or IP address of the device to manage in iWorkflow.
    required: True
  pool:
    description:
      - The license pool that you want to add the member to.
  state:
    description:
      - Whether the managed device should exist, or not, in iWorkflow.
    required: false
    default: present
    choices:
      - present
      - absent
notes:
  - Requires the f5-sdk Python package on the host. This is as easy as pip
    install f5-sdk.
extends_documentation_fragment: f5
requirements:
    - f5-sdk >= 2.2.0
    - iWorkflow >= 2.1.0
author:
    - Tim Rupp (@caphrim007)
'''

EXAMPLES = '''

'''

RETURN = '''

'''

import time

try:
    from f5.iworkflow import ManagementRoot
    from icontrol.session import iControlUnexpectedHTTPError
    HAS_F5SDK = True
except ImportError:
    HAS_F5SDK = False


from ansible.module_utils.basic import *
from ansible.module_utils.f5 import *


def connect_to_f5(**kwargs):
    return ManagementRoot(kwargs['server'],
                          kwargs['user'],
                          kwargs['password'],
                          port=kwargs['server_port'],
                          token='local')


class iWorkflowLicensePoolMemberParams(object):
    device = None
    username_credential = None
    password_credential = None
    pool = None

    def difference(self, obj):
        """Compute difference between one object and another

        :param obj:
        Returns:
            Returns a new set with elements in s but not in t (s - t)
        """
        excluded_keys = [
            'password', 'server', 'user', 'server_port', 'validate_certs',
            'username_credential', 'password_credential'
        ]
        return self._difference(self, obj, excluded_keys)

    def _difference(self, obj1, obj2, excluded_keys):
        """

        Code take from https://www.djangosnippets.org/snippets/2281/

        :param obj1:
        :param obj2:
        :param excluded_keys:
        :return:
        """
        d1, d2 = obj1.__dict__, obj2.__dict__
        new = {}
        for k,v in d1.items():
            if k in excluded_keys:
                continue
            try:
                if v != d2[k]:
                    new.update({k: d2[k]})
            except KeyError:
                new.update({k: v})
        return new

    @classmethod
    def from_module(cls, module):
        """Create instance from dictionary of Ansible Module params

        This method accepts a dictionary that is in the form supplied by
        the

        Args:
             module: An AnsibleModule object's `params` attribute.

        Returns:
            A new instance of iWorkflowSystemSetupParams. The attributes
            of this object are set according to the param data that is
            supplied by the user.
        """
        result = cls()
        for key in module:
            setattr(result, key, module[key])
        return result


class iWorkflowLicensePoolMemberModule(AnsibleModule):
    def __init__(self):
        self.argument_spec = dict()
        self.meta_args = dict()
        self.supports_check_mode = True
        self.init_meta_args()
        self.init_argument_spec()
        super(iWorkflowLicensePoolMemberModule, self).__init__(
            argument_spec=self.argument_spec,
            supports_check_mode=self.supports_check_mode,
            required_if=[
                ['state', 'absent', ['device', 'username_credential', 'password_credential']]
            ]
        )

    def __set__(self, instance, value):
        if isinstance(value, iWorkflowLicensePoolMemberModule):
            instance.params = iWorkflowLicensePoolMemberParams.from_module(
                self.params
            )
        else:
            super(iWorkflowLicensePoolMemberModule, self).__set__(instance, value)

    def init_meta_args(self):
        args = dict(
            device=dict(default=None),
            pool=dict(required=True),
            state=dict(
                required=False,
                default='present',
                choices=['absent', 'present']
            )
        )
        self.meta_args = args

    def init_argument_spec(self):
        self.argument_spec = f5_argument_spec()
        self.argument_spec.update(self.meta_args)


class iWorkflowLicensePoolMemberManager(object):
    params = iWorkflowLicensePoolMemberParams()
    current = iWorkflowLicensePoolMemberParams()
    module = iWorkflowLicensePoolMemberModule()

    def __init__(self):
        self.api = None
        self.changes = None
        self.config = None

    def apply_changes(self):
        """Apply the user's changes to the device

        This method is the primary entry-point to this module. Based on the
        parameters supplied by the user to the class, this method will
        determine which `state` needs to be fulfilled and delegate the work
        to more specialized helper methods.

        Additionally, this method will return the result of applying the
        changes so that Ansible can communicate this result to the user.

        Raises:
            F5ModuleError: An error occurred communicating with the device
        """
        result = dict()
        state = self.params.state

        try:
            self.api = connect_to_f5(**self.params.__dict__)
            if state == "present":
                changed = self.present()
            elif state == "absent":
                changed = self.absent()
        except iControlUnexpectedHTTPError as e:
            raise F5ModuleError(str(e))

        changes = self.params.difference(self.current)
        result.update(**changes)
        result.update(dict(changed=changed))
        return result

    def exists(self):
        if not self.pool_exists():
            raise F5ModuleError(
                "The specified pool does not exist"
            )
        if not self.device_exists():
            raise F5ModuleError(
                "The specified device does not exist"
            )
        device = self.get_device()
        pool = self.get_pool()
        return self.pool_member_exists(pool, device)

    def device_exists(self):
        dg = self.api.shared.resolver.device_groups
        devices = dg.cm_cloud_managed_devices.devices_s.get_collection(
            requests_params=dict(
                params="$filter=address+eq+'{0}'".format(self.params.device)
            )
        )

        if len(devices) == 1:
            return True
        elif len(devices) == 0:
            return False
        else:
            raise F5ModuleError(
                "Multiple managed devices with the provided device address were found!"
            )

    def pool_exists(self):
        pools = self.api.cm.shared.licensing.pools_s.get_collection(
            requests_params=dict(
                params="$filter=name+eq+'{0}'".format(self.params.pool)
            )
        )

        if len(pools) == 1:
            return True
        elif len(pools) == 0:
            return False
        else:
            raise F5ModuleError(
                "Multiple license pools with the provided name were found!"
            )

    def get_pool(self):
        pools = self.api.cm.shared.licensing.pools_s.get_collection(
            requests_params=dict(
                params="$filter=name+eq+'{0}'".format(self.params.pool)
            )
        )
        return pools.pop()

    def get_device(self):
        dg = self.api.shared.resolver.device_groups
        devices = dg.cm_cloud_managed_devices.devices_s.get_collection(
            requests_params=dict(
                params="$filter=address+eq+'{0}'".format(self.params.device)
            )
        )
        return devices.pop()

    def pool_member_exists(self, pool, device):
        members = pool.members_s.get_collection()
        for member in members:
            if member.deviceReference['link'] == device.selfLink:
                return True
        return False

    def present(self):
        if self.exists():
            return False
        else:
            return self.create_pool_member()

    def create_pool_member(self):
        if self.module.check_mode:
            return True
        self.create_pool_member_on_device()
        return True

    def create_pool_member_on_device(self):
        device = self.get_device()
        pool = self.get_pool()
        member = pool.members_s.member.create(
            deviceReference=dict(
                link=device.selfLink
            )
        )
        return self.wait_for_pool_member_state_to_license(member)

    def wait_for_pool_member_state_to_license(self, member):
        error_values = ['FAILED']
        # Wait no more than half an hour
        for x in range(1, 180):
            member.refresh()
            if member.state == 'LICENSED':
                break
            elif member.state in error_values:
                raise F5ModuleError(member.errors)
            time.sleep(10)

    def absent(self):
        if self.exists():
            return self.remove_pool_member()
        return False

    def remove_pool_member(self):
        if self.module.check_mode:
            return True
        self.remove_pool_member_from_device()
        if self.exists():
            raise F5ModuleError("Failed to remove the pool member")
        return True

    def remove_pool_member_from_device(self):
        result = None
        device = self.get_device()
        members = pool.members.get_collection()
        for member in members:
            if member.deviceReference['link'] != device.selfLink:
                continue
            result = member
        if result:
            member.delete()
            return True
        raise F5ModuleError(
            "Failed to delete the member from the pool"
        )


def main():
    if not HAS_F5SDK:
        raise F5ModuleError("The python f5-sdk module is required")

    module = iWorkflowLicensePoolMemberModule()

    try:
        obj = iWorkflowLicensePoolMemberManager()
        obj.module = module
        result = obj.apply_changes()
        module.exit_json(**result)
    except F5ModuleError as e:
        module.fail_json(msg=str(e))

if __name__ == '__main__':
    main()
