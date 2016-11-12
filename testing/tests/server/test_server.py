# -*- coding: utf-8 -*-
# test_server.py
# Copyright (C) 2013 LEAP
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.
"""
Tests for server-related functionality.
"""
import binascii
import mock
import os
import pytest

from hashlib import sha512
from pkg_resources import resource_filename
from urlparse import urljoin
from uuid import uuid4

from twisted.internet import defer
from twisted.trial import unittest

from leap.soledad.common.couch.state import CouchServerState
from leap.soledad.common.couch import CouchDatabase
from test_soledad.u1db_tests import TestCaseWithServer
from test_soledad.util import CouchDBTestCase
from test_soledad.util import (
    make_token_soledad_app,
    make_soledad_document_for_test,
    soledad_sync_target,
    BaseSoledadTest,
)

from leap.soledad.client import _crypto
from leap.soledad.client import Soledad
from leap.soledad.server.config import load_configuration
from leap.soledad.server.config import CONFIG_DEFAULTS
from leap.soledad.server.auth import URLToAuthorization
from leap.soledad.server.auth import SoledadTokenAuthMiddleware


class ServerAuthenticationMiddlewareTestCase(CouchDBTestCase):

    def setUp(self):
        super(ServerAuthenticationMiddlewareTestCase, self).setUp()
        app = mock.Mock()
        self._state = CouchServerState(self.couch_url)
        app.state = self._state
        self.auth_middleware = SoledadTokenAuthMiddleware(app)
        self._authorize('valid-uuid', 'valid-token')

    def _authorize(self, uuid, token):
        token_doc = {}
        token_doc['_id'] = sha512(token).hexdigest()
        token_doc[self._state.TOKENS_USER_ID_KEY] = uuid
        token_doc[self._state.TOKENS_TYPE_KEY] = \
            self._state.TOKENS_TYPE_DEF
        dbname = self._state._tokens_dbname()
        db = self.couch_server.create(dbname)
        db.save(token_doc)
        self.addCleanup(self.delete_db, db.name)

    def test_authorized_user(self):
        is_authorized = self.auth_middleware._verify_authentication_data
        self.assertTrue(is_authorized('valid-uuid', 'valid-token'))
        self.assertFalse(is_authorized('valid-uuid', 'invalid-token'))
        self.assertFalse(is_authorized('invalid-uuid', 'valid-token'))
        self.assertFalse(is_authorized('eve', 'invalid-token'))


class ServerAuthorizationTestCase(BaseSoledadTest):

    """
    Tests related to Soledad server authorization.
    """

    def setUp(self):
        pass

    def tearDown(self):
        pass

    def _make_environ(self, path_info, request_method):
        return {
            'PATH_INFO': path_info,
            'REQUEST_METHOD': request_method,
        }

    def test_verify_action_with_correct_dbnames(self):
        """
        Test encrypting and decrypting documents.

        The following table lists the authorized actions among all possible
        u1db remote actions:

            URL path                      | Authorized actions
            --------------------------------------------------
            /                             | GET
            /shared-db                    | GET
            /shared-db/docs               | -
            /shared-db/doc/{id}           | GET, PUT, DELETE
            /shared-db/sync-from/{source} | -
            /user-db                      | GET, PUT, DELETE
            /user-db/docs                 | -
            /user-db/doc/{id}             | -
            /user-db/sync-from/{source}   | GET, PUT, POST
        """
        uuid = uuid4().hex
        authmap = URLToAuthorization(uuid,)
        dbname = authmap._user_db_name
        # test global auth
        self.assertTrue(
            authmap.is_authorized(self._make_environ('/', 'GET')))
        # test shared-db database resource auth
        self.assertTrue(
            authmap.is_authorized(
                self._make_environ('/shared', 'GET')))
        self.assertFalse(
            authmap.is_authorized(
                self._make_environ('/shared', 'PUT')))
        self.assertFalse(
            authmap.is_authorized(
                self._make_environ('/shared', 'DELETE')))
        self.assertFalse(
            authmap.is_authorized(
                self._make_environ('/shared', 'POST')))
        # test shared-db docs resource auth
        self.assertFalse(
            authmap.is_authorized(
                self._make_environ('/shared/docs', 'GET')))
        self.assertFalse(
            authmap.is_authorized(
                self._make_environ('/shared/docs', 'PUT')))
        self.assertFalse(
            authmap.is_authorized(
                self._make_environ('/shared/docs', 'DELETE')))
        self.assertFalse(
            authmap.is_authorized(
                self._make_environ('/shared/docs', 'POST')))
        # test shared-db doc resource auth
        self.assertTrue(
            authmap.is_authorized(
                self._make_environ('/shared/doc/x', 'GET')))
        self.assertTrue(
            authmap.is_authorized(
                self._make_environ('/shared/doc/x', 'PUT')))
        self.assertTrue(
            authmap.is_authorized(
                self._make_environ('/shared/doc/x', 'DELETE')))
        self.assertFalse(
            authmap.is_authorized(
                self._make_environ('/shared/doc/x', 'POST')))
        # test shared-db sync resource auth
        self.assertFalse(
            authmap.is_authorized(
                self._make_environ('/shared/sync-from/x', 'GET')))
        self.assertFalse(
            authmap.is_authorized(
                self._make_environ('/shared/sync-from/x', 'PUT')))
        self.assertFalse(
            authmap.is_authorized(
                self._make_environ('/shared/sync-from/x', 'DELETE')))
        self.assertFalse(
            authmap.is_authorized(
                self._make_environ('/shared/sync-from/x', 'POST')))
        # test user-db database resource auth
        self.assertTrue(
            authmap.is_authorized(
                self._make_environ('/%s' % dbname, 'GET')))
        self.assertTrue(
            authmap.is_authorized(
                self._make_environ('/%s' % dbname, 'PUT')))
        self.assertTrue(
            authmap.is_authorized(
                self._make_environ('/%s' % dbname, 'DELETE')))
        self.assertFalse(
            authmap.is_authorized(
                self._make_environ('/%s' % dbname, 'POST')))
        # test user-db docs resource auth
        self.assertFalse(
            authmap.is_authorized(
                self._make_environ('/%s/docs' % dbname, 'GET')))
        self.assertFalse(
            authmap.is_authorized(
                self._make_environ('/%s/docs' % dbname, 'PUT')))
        self.assertFalse(
            authmap.is_authorized(
                self._make_environ('/%s/docs' % dbname, 'DELETE')))
        self.assertFalse(
            authmap.is_authorized(
                self._make_environ('/%s/docs' % dbname, 'POST')))
        # test user-db doc resource auth
        self.assertFalse(
            authmap.is_authorized(
                self._make_environ('/%s/doc/x' % dbname, 'GET')))
        self.assertFalse(
            authmap.is_authorized(
                self._make_environ('/%s/doc/x' % dbname, 'PUT')))
        self.assertFalse(
            authmap.is_authorized(
                self._make_environ('/%s/doc/x' % dbname, 'DELETE')))
        self.assertFalse(
            authmap.is_authorized(
                self._make_environ('/%s/doc/x' % dbname, 'POST')))
        # test user-db sync resource auth
        self.assertTrue(
            authmap.is_authorized(
                self._make_environ('/%s/sync-from/x' % dbname, 'GET')))
        self.assertTrue(
            authmap.is_authorized(
                self._make_environ('/%s/sync-from/x' % dbname, 'PUT')))
        self.assertFalse(
            authmap.is_authorized(
                self._make_environ('/%s/sync-from/x' % dbname, 'DELETE')))
        self.assertTrue(
            authmap.is_authorized(
                self._make_environ('/%s/sync-from/x' % dbname, 'POST')))

    def test_verify_action_with_wrong_dbnames(self):
        """
        Test if authorization fails for a wrong dbname.
        """
        uuid = uuid4().hex
        authmap = URLToAuthorization(uuid)
        dbname = 'somedb'
        # test wrong-db database resource auth
        self.assertFalse(
            authmap.is_authorized(
                self._make_environ('/%s' % dbname, 'GET')))
        self.assertFalse(
            authmap.is_authorized(
                self._make_environ('/%s' % dbname, 'PUT')))
        self.assertFalse(
            authmap.is_authorized(
                self._make_environ('/%s' % dbname, 'DELETE')))
        self.assertFalse(
            authmap.is_authorized(
                self._make_environ('/%s' % dbname, 'POST')))
        # test wrong-db docs resource auth
        self.assertFalse(
            authmap.is_authorized(
                self._make_environ('/%s/docs' % dbname, 'GET')))
        self.assertFalse(
            authmap.is_authorized(
                self._make_environ('/%s/docs' % dbname, 'PUT')))
        self.assertFalse(
            authmap.is_authorized(
                self._make_environ('/%s/docs' % dbname, 'DELETE')))
        self.assertFalse(
            authmap.is_authorized(
                self._make_environ('/%s/docs' % dbname, 'POST')))
        # test wrong-db doc resource auth
        self.assertFalse(
            authmap.is_authorized(
                self._make_environ('/%s/doc/x' % dbname, 'GET')))
        self.assertFalse(
            authmap.is_authorized(
                self._make_environ('/%s/doc/x' % dbname, 'PUT')))
        self.assertFalse(
            authmap.is_authorized(
                self._make_environ('/%s/doc/x' % dbname, 'DELETE')))
        self.assertFalse(
            authmap.is_authorized(
                self._make_environ('/%s/doc/x' % dbname, 'POST')))
        # test wrong-db sync resource auth
        self.assertFalse(
            authmap.is_authorized(
                self._make_environ('/%s/sync-from/x' % dbname, 'GET')))
        self.assertFalse(
            authmap.is_authorized(
                self._make_environ('/%s/sync-from/x' % dbname, 'PUT')))
        self.assertFalse(
            authmap.is_authorized(
                self._make_environ('/%s/sync-from/x' % dbname, 'DELETE')))
        self.assertFalse(
            authmap.is_authorized(
                self._make_environ('/%s/sync-from/x' % dbname, 'POST')))


@pytest.mark.usefixtures("method_tmpdir")
class EncryptedSyncTestCase(
        CouchDBTestCase, TestCaseWithServer):

    """
    Tests for encrypted sync using Soledad server backed by a couch database.
    """

    # increase twisted.trial's timeout because large files syncing might take
    # some time to finish.
    timeout = 500

    @staticmethod
    def make_app_with_state(state):
        return make_token_soledad_app(state)

    make_document_for_test = make_soledad_document_for_test

    sync_target = soledad_sync_target

    def _soledad_instance(self, user=None, passphrase=u'123',
                          prefix='',
                          secrets_path='secrets.json',
                          local_db_path='soledad.u1db',
                          server_url='',
                          cert_file=None, auth_token=None):
        """
        Instantiate Soledad.
        """

        # this callback ensures we save a document which is sent to the shared
        # db.
        def _put_doc_side_effect(doc):
            self._doc_put = doc

        if not server_url:
            # attempt to find the soledad server url
            server_address = None
            server = getattr(self, 'server', None)
            if server:
                server_address = getattr(self.server, 'server_address', None)
            else:
                host = self.port.getHost()
                server_address = (host.host, host.port)
            if server_address:
                server_url = 'http://%s:%d' % (server_address)

        return Soledad(
            user,
            passphrase,
            secrets_path=os.path.join(self.tempdir, prefix, secrets_path),
            local_db_path=os.path.join(
                self.tempdir, prefix, local_db_path),
            server_url=server_url,
            cert_file=cert_file,
            auth_token=auth_token,
            shared_db=self.get_default_shared_mock(_put_doc_side_effect))

    def make_app(self):
        self.request_state = CouchServerState(self.couch_url)
        return self.make_app_with_state(self.request_state)

    def setUp(self):
        CouchDBTestCase.setUp(self)
        TestCaseWithServer.setUp(self)

    def tearDown(self):
        CouchDBTestCase.tearDown(self)
        TestCaseWithServer.tearDown(self)

    def _test_encrypted_sym_sync(self, passphrase=u'123', doc_size=2,
                                 number_of_docs=1):
        """
        Test the complete syncing chain between two soledad dbs using a
        Soledad server backed by a couch database.
        """
        self.startTwistedServer()
        user = 'user-' + uuid4().hex

        # this will store all docs ids to avoid get_all_docs
        created_ids = []

        # instantiate soledad and create a document
        sol1 = self._soledad_instance(
            user=user,
            # token is verified in test_target.make_token_soledad_app
            auth_token='auth-token',
            passphrase=passphrase)

        # instantiate another soledad using the same secret as the previous
        # one (so we can correctly verify the mac of the synced document)
        sol2 = self._soledad_instance(
            user=user,
            prefix='x',
            auth_token='auth-token',
            secrets_path=sol1._secrets_path,
            passphrase=passphrase)

        # ensure remote db exists before syncing
        db = CouchDatabase.open_database(
            urljoin(self.couch_url, 'user-' + user),
            create=True)

        def _db1AssertEmptyDocList(results):
            _, doclist = results
            self.assertEqual([], doclist)

        def _db1CreateDocs(results):
            deferreds = []
            for i in xrange(number_of_docs):
                content = binascii.hexlify(os.urandom(doc_size / 2))
                d = sol1.create_doc({'data': content})
                d.addCallback(created_ids.append)
                deferreds.append(d)
            return defer.DeferredList(deferreds)

        def _db1AssertDocsSyncedToServer(results):
            self.assertEqual(number_of_docs, len(created_ids))
            for soldoc in created_ids:
                couchdoc = db.get_doc(soldoc.doc_id)
                self.assertTrue(couchdoc)
                # assert document structure in couch server
                self.assertEqual(soldoc.doc_id, couchdoc.doc_id)
                self.assertEqual(soldoc.rev, couchdoc.rev)
                couch_content = couchdoc.content.keys()
                self.assertEqual(['raw'], couch_content)
                self.assertTrue(_crypto.is_symmetrically_encrypted(couchdoc))

        d = sol1.get_all_docs()
        d.addCallback(_db1AssertEmptyDocList)
        d.addCallback(_db1CreateDocs)
        d.addCallback(lambda _: sol1.sync())
        d.addCallback(_db1AssertDocsSyncedToServer)

        def _db2AssertEmptyDocList(results):
            _, doclist = results
            self.assertEqual([], doclist)

        def _getAllDocsFromBothDbs(results):
            d1 = sol1.get_all_docs()
            d2 = sol2.get_all_docs()
            return defer.DeferredList([d1, d2])

        d.addCallback(lambda _: sol2.get_all_docs())
        d.addCallback(_db2AssertEmptyDocList)
        d.addCallback(lambda _: sol2.sync())
        d.addCallback(_getAllDocsFromBothDbs)

        def _assertDocSyncedFromDb1ToDb2(results):
            r1, r2 = results
            _, (gen1, doclist1) = r1
            _, (gen2, doclist2) = r2
            self.assertEqual(number_of_docs, gen1)
            self.assertEqual(number_of_docs, gen2)
            self.assertEqual(number_of_docs, len(doclist1))
            self.assertEqual(number_of_docs, len(doclist2))
            self.assertEqual(doclist1[0], doclist2[0])

        d.addCallback(_assertDocSyncedFromDb1ToDb2)

        def _cleanUp(results):
            db.delete_database()
            db.close()
            sol1.close()
            sol2.close()

        d.addCallback(_cleanUp)

        return d

    def test_encrypted_sym_sync(self):
        return self._test_encrypted_sym_sync()

    def test_encrypted_sym_sync_with_unicode_passphrase(self):
        """
        Test the complete syncing chain between two soledad dbs using a
        Soledad server backed by a couch database, using an unicode
        passphrase.
        """
        return self._test_encrypted_sym_sync(passphrase=u'ãáàäéàëíìïóòöõúùüñç')

    def test_sync_many_small_files(self):
        """
        Test if Soledad can sync many smallfiles.
        """
        return self._test_encrypted_sym_sync(doc_size=2, number_of_docs=100)


class ConfigurationParsingTest(unittest.TestCase):

    def setUp(self):
        self.maxDiff = None

    def test_use_defaults_on_failure(self):
        config = load_configuration('this file will never exist')
        expected = CONFIG_DEFAULTS
        self.assertEquals(expected, config)

    def test_security_values_configuration(self):
        # given
        config_path = resource_filename('test_soledad',
                                        'fixture_soledad.conf')
        # when
        config = load_configuration(config_path)

        # then
        expected = {'members': ['user1', 'user2'],
                    'members_roles': ['role1', 'role2'],
                    'admins': ['user3', 'user4'],
                    'admins_roles': ['role3', 'role3']}
        self.assertDictEqual(expected, config['database-security'])

    def test_server_values_configuration(self):
        # given
        config_path = resource_filename('test_soledad',
                                        'fixture_soledad.conf')
        # when
        config = load_configuration(config_path)

        # then
        expected = {'couch_url':
                    'http://soledad:passwd@localhost:5984',
                    'create_cmd':
                    'sudo -u soledad-admin /usr/bin/create-user-db',
                    'admin_netrc':
                    '/etc/couchdb/couchdb-soledad-admin.netrc',
                    'batching': False}
        self.assertDictEqual(expected, config['soledad-server'])
