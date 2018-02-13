# Copyright 2012 Nebula Inc
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

from mox3.mox import IsA
import six
import yaml

from django.core.urlresolvers import reverse
from django.http import HttpRequest
from django import template
from django.template import loader
from django.test.utils import override_settings

from openstack_dashboard import api
from openstack_dashboard.test import helpers as test


INDEX_URL = reverse('horizon:project:api_access:index')
API_URL = "horizon:project:api_access"
EC2_URL = reverse(API_URL + ":ec2")
OPENRC_URL = reverse(API_URL + ":openrc")
OPENRCV2_URL = reverse(API_URL + ":openrcv2")
CREDS_URL = reverse(API_URL + ":view_credentials")
RECREATE_CREDS_URL = reverse(API_URL + ":recreate_credentials")


class APIAccessTests(test.TestCase):
    def test_ec2_download_view(self):
        creds = self.ec2.first()

        self.mox.StubOutWithMock(api.keystone, "list_ec2_credentials")
        self.mox.StubOutWithMock(api.keystone, "create_ec2_credentials")

        api.keystone.list_ec2_credentials(IsA(HttpRequest), self.user.id) \
                    .AndReturn([])
        api.keystone.create_ec2_credentials(IsA(HttpRequest),
                                            self.user.id,
                                            self.tenant.id).AndReturn(creds)
        self.mox.ReplayAll()

        res = self.client.get(EC2_URL)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res['content-type'], 'application/zip')

    def test_openrcv2_credentials(self):
        res = self.client.get(OPENRCV2_URL)
        self.assertEqual(res.status_code, 200)
        openrc = 'project/api_access/openrc_v2.sh.template'
        self.assertTemplateUsed(res, openrc)
        name = 'export OS_USERNAME="{}"'.format(self.request.user.username)
        t_id = 'export OS_TENANT_ID={}'.format(self.request.user.tenant_id)
        domain = 'export OS_USER_DOMAIN_NAME="{}"'.format(
            self.request.user.user_domain_name)
        self.assertIn(name.encode('utf-8'), res.content)
        self.assertIn(t_id.encode('utf-8'), res.content)
        # domain content should not be present for v2
        self.assertNotIn(domain.encode('utf-8'), res.content)

    @override_settings(OPENSTACK_API_VERSIONS={"identity": 3})
    def test_openrc_credentials(self):
        res = self.client.get(OPENRC_URL)
        self.assertEqual(res.status_code, 200)
        openrc = 'project/api_access/openrc.sh.template'
        self.assertTemplateUsed(res, openrc)
        name = 'export OS_USERNAME="{}"'.format(self.request.user.username)
        p_id = 'export OS_PROJECT_ID={}'.format(self.request.user.tenant_id)
        domain = 'export OS_USER_DOMAIN_NAME="{}"'.format(
            self.request.user.user_domain_name)
        self.assertIn(name.encode('utf-8'), res.content)
        self.assertIn(p_id.encode('utf-8'), res.content)
        self.assertIn(domain.encode('utf-8'), res.content)

    @test.create_stubs({api.keystone: ("list_ec2_credentials",)})
    def test_credential_api(self):
        certs = self.ec2.list()
        api.keystone.list_ec2_credentials(IsA(HttpRequest), self.user.id) \
            .AndReturn(certs)

        self.mox.ReplayAll()

        res = self.client.get(CREDS_URL)
        self.assertEqual(res.status_code, 200)
        credentials = 'project/api_access/credentials.html'
        self.assertTemplateUsed(res, credentials)
        self.assertEqual(self.user.id, res.context['openrc_creds']['user'].id)
        self.assertEqual(certs[0].access,
                         res.context['ec2_creds']['ec2_access_key'])

    @test.create_stubs({api.keystone: ("list_ec2_credentials",
                                       "create_ec2_credentials",
                                       "delete_user_ec2_credentials",)})
    def _test_recreate_user_credentials(self, exists_credentials=True):
        old_creds = self.ec2.list() if exists_credentials else []
        new_creds = self.ec2.first()
        api.keystone.list_ec2_credentials(
            IsA(HttpRequest),
            self.user.id).AndReturn(old_creds)
        if exists_credentials:
            api.keystone.delete_user_ec2_credentials(
                IsA(HttpRequest),
                self.user.id,
                old_creds[0].access).AndReturn([])
        api.keystone.create_ec2_credentials(
            IsA(HttpRequest),
            self.user.id,
            self.tenant.id).AndReturn(new_creds)

        self.mox.ReplayAll()

        res_get = self.client.get(RECREATE_CREDS_URL)
        self.assertEqual(res_get.status_code, 200)
        credentials = \
            'project/api_access/recreate_credentials.html'
        self.assertTemplateUsed(res_get, credentials)

        res_post = self.client.post(RECREATE_CREDS_URL)
        self.assertNoFormErrors(res_post)
        self.assertRedirectsNoFollow(res_post, INDEX_URL)

    def test_recreate_user_credentials(self):
        self._test_recreate_user_credentials()

    def test_recreate_user_credentials_with_no_existing_creds(self):
        self._test_recreate_user_credentials(exists_credentials=False)


class ASCIITenantNameRCTests(test.TestCase):
    TENANT_NAME = 'tenant'

    def _setup_user(self, **kwargs):
        super(ASCIITenantNameRCTests, self)._setup_user(
            tenant_name=self.TENANT_NAME)

    def test_openrcv2_credentials_filename(self):
        expected = 'attachment; filename="%s-openrc.sh"' % self.TENANT_NAME
        res = self.client.get(OPENRCV2_URL)

        self.assertEqual(res.status_code, 200)
        self.assertEqual(expected, res['content-disposition'])

    @override_settings(OPENSTACK_API_VERSIONS={"identity": 3})
    def test_openrc_credentials_filename(self):
        expected = 'attachment; filename="%s-openrc.sh"' % self.TENANT_NAME
        res = self.client.get(OPENRC_URL)

        self.assertEqual(res.status_code, 200)
        self.assertEqual(expected, res['content-disposition'])


class UnicodeTenantNameRCTests(test.TestCase):
    TENANT_NAME = u'\u043f\u0440\u043e\u0435\u043a\u0442'

    def _setup_user(self, **kwargs):
        super(UnicodeTenantNameRCTests, self)._setup_user(
            tenant_name=self.TENANT_NAME)

    def test_openrcv2_credentials_filename(self):
        expected = ('attachment; filename="%s-openrc.sh"' %
                    self.TENANT_NAME).encode('utf-8')
        res = self.client.get(OPENRCV2_URL)

        self.assertEqual(res.status_code, 200)

        result_content_disposition = res['content-disposition']
        # we need to encode('latin-1') because django response object
        # has custom setter which encodes all values to latin-1 for Python3.
        # https://github.com/django/django/blob/1.9.6/django/http/response.py#L142
        # see _convert_to_charset() method for details.
        if six.PY3:
            result_content_disposition = result_content_disposition.\
                encode('latin-1')
        self.assertEqual(expected,
                         result_content_disposition)

    @override_settings(OPENSTACK_API_VERSIONS={"identity": 3})
    def test_openrc_credentials_filename(self):
        expected = ('attachment; filename="%s-openrc.sh"' %
                    self.TENANT_NAME).encode('utf-8')
        res = self.client.get(OPENRC_URL)

        self.assertEqual(res.status_code, 200)

        result_content_disposition = res['content-disposition']

        if six.PY3:
            result_content_disposition = result_content_disposition.\
                encode('latin-1')
        self.assertEqual(expected,
                         result_content_disposition)


class FakeUser(object):
    username = "cool user"


class TemplateRenderTest(test.TestCase):
    """Tests for templates render."""

    def test_openrc_html_escape(self):
        context = {
            "user": FakeUser(),
            "tenant_id": "some-cool-id",
            "auth_url": "http://tests.com",
            "tenant_name": "ENG Perf R&D"}
        out = loader.render_to_string(
            'project/api_access/openrc.sh.template',
            context,
            template.Context(context))

        self.assertNotIn("&amp;", out)
        self.assertIn("ENG Perf R&D", out)

    def test_openrc_html_evil_shell_escape(self):
        context = {
            "user": FakeUser(),
            "tenant_id": "some-cool-id",
            "auth_url": "http://tests.com",
            "tenant_name": 'o"; sudo rm -rf /'}
        out = loader.render_to_string(
            'project/api_access/openrc.sh.template',
            context,
            template.Context(context))

        self.assertNotIn('o"', out)
        self.assertIn('\"', out)

    def test_openrc_html_evil_shell_backslash_escape(self):
        context = {
            "user": FakeUser(),
            "tenant_id": "some-cool-id",
            "auth_url": "http://tests.com",
            "tenant_name": 'o\"; sudo rm -rf /'}
        out = loader.render_to_string(
            'project/api_access/openrc.sh.template',
            context,
            template.Context(context))

        self.assertNotIn('o\"', out)
        self.assertNotIn('o"', out)
        self.assertIn('\\"', out)

    def test_openrc_set_region(self):
        context = {
            "user": FakeUser(),
            "tenant_id": "some-cool-id",
            "auth_url": "http://tests.com",
            "tenant_name": "Tenant",
            "region": "Colorado"}
        out = loader.render_to_string(
            'project/api_access/openrc.sh.template',
            context,
            template.Context(context))

        self.assertIn("OS_REGION_NAME=\"Colorado\"", out)

    def test_openrc_region_not_set(self):
        context = {
            "user": FakeUser(),
            "tenant_id": "some-cool-id",
            "auth_url": "http://tests.com",
            "tenant_name": "Tenant"}
        out = loader.render_to_string(
            'project/api_access/openrc.sh.template',
            context,
            template.Context(context))

        self.assertIn("OS_REGION_NAME=\"\"", out)

    def test_clouds_yaml_set_region(self):
        context = {
            "cloud_name": "openstack",
            "user": FakeUser(),
            "tenant_id": "some-cool-id",
            "auth_url": "http://example.com",
            "tenant_name": "Tenant",
            "region": "Colorado"}
        out = yaml.safe_load(loader.render_to_string(
            'project/api_access/clouds.yaml.template',
            context,
            template.Context(context)))

        self.assertIn('clouds', out)
        self.assertIn('openstack', out['clouds'])
        self.assertNotIn('profile', out['clouds']['openstack'])
        self.assertEqual(
            "http://example.com",
            out['clouds']['openstack']['auth']['auth_url'])
        self.assertEqual("Colorado", out['clouds']['openstack']['region_name'])
        self.assertNotIn('regions', out['clouds']['openstack'])

    def test_clouds_yaml_region_not_set(self):
        context = {
            "cloud_name": "openstack",
            "user": FakeUser(),
            "tenant_id": "some-cool-id",
            "auth_url": "http://example.com",
            "tenant_name": "Tenant"}
        out = yaml.safe_load(loader.render_to_string(
            'project/api_access/clouds.yaml.template',
            context,
            template.Context(context)))

        self.assertIn('clouds', out)
        self.assertIn('openstack', out['clouds'])
        self.assertNotIn('profile', out['clouds']['openstack'])
        self.assertEqual(
            "http://example.com",
            out['clouds']['openstack']['auth']['auth_url'])
        self.assertNotIn('region_name', out['clouds']['openstack'])
        self.assertNotIn('regions', out['clouds']['openstack'])

    def test_clouds_yaml_regions(self):
        regions = ['region1', 'region2']
        context = {
            "cloud_name": "openstack",
            "user": FakeUser(),
            "tenant_id": "some-cool-id",
            "auth_url": "http://example.com",
            "tenant_name": "Tenant",
            "regions": regions}
        out = yaml.safe_load(loader.render_to_string(
            'project/api_access/clouds.yaml.template',
            context,
            template.Context(context)))

        self.assertIn('clouds', out)
        self.assertIn('openstack', out['clouds'])
        self.assertNotIn('profile', out['clouds']['openstack'])
        self.assertEqual(
            "http://example.com",
            out['clouds']['openstack']['auth']['auth_url'])
        self.assertNotIn('region_name', out['clouds']['openstack'])
        self.assertIn('regions', out['clouds']['openstack'])
        self.assertEqual(regions, out['clouds']['openstack']['regions'])

    def test_clouds_yaml_profile(self):
        regions = ['region1', 'region2']
        context = {
            "cloud_name": "openstack",
            "user": FakeUser(),
            "profile": "example",
            "tenant_id": "some-cool-id",
            "auth_url": "http://example.com",
            "tenant_name": "Tenant",
            "regions": regions}
        out = yaml.safe_load(loader.render_to_string(
            'project/api_access/clouds.yaml.template',
            context,
            template.Context(context)))

        self.assertIn('clouds', out)
        self.assertIn('openstack', out['clouds'])
        self.assertIn('profile', out['clouds']['openstack'])
        self.assertEqual('example', out['clouds']['openstack']['profile'])
        self.assertNotIn('auth_url', out['clouds']['openstack']['auth'])
        self.assertNotIn('region_name', out['clouds']['openstack'])
        self.assertNotIn('regions', out['clouds']['openstack'])
