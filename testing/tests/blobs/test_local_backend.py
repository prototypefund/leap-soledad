# -*- coding: utf-8 -*-
# test_local_backend.py
# Copyright (C) 2017 LEAP
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
Tests for sqlcipher backend on blobs client.
"""
from twisted.trial import unittest
from twisted.internet import defer
from leap.soledad.client._blobs import BlobManager, BlobDoc
from io import BytesIO
from mock import Mock
import pytest
import os


class BlobManagerTestCase(unittest.TestCase):

    class doc_info:
        doc_id = 'D-deadbeef'
        rev = '397932e0c77f45fcb7c3732930e7e9b2:1'

    def setUp(self):
        self.cleartext = BytesIO('rosa de foc')
        self.secret = 'A' * 96
        self.manager = BlobManager(
            self.tempdir, '',
            'A' * 32, self.secret,
            'uuid', 'token', None)
        self.addCleanup(self.manager.close)

    @defer.inlineCallbacks
    @pytest.mark.usefixtures("method_tmpdir")
    def test_get_inexistent(self):
        self.manager._download_and_decrypt = Mock(return_value=None)
        args = ('inexistent_blob_id', 'inexistent_doc_id', 'inexistent_rev')
        result = yield self.manager.get(*args)
        self.assertIsNone(result)
        self.manager._download_and_decrypt.assert_called_once_with(*args)

    @defer.inlineCallbacks
    @pytest.mark.usefixtures("method_tmpdir")
    def test_get_from_existing_value(self):
        self.manager._download_and_decrypt = Mock(return_value=None)
        msg = "It's me, M4r10!"
        yield self.manager.local.put('myblob_id', BytesIO(msg),
                                     size=len(msg))
        args = ('myblob_id', 'mydoc_id', 'cool_rev')
        result = yield self.manager.get(*args)
        self.assertEquals(result.getvalue(), msg)
        self.assertNot(self.manager._download_and_decrypt.called)

    @defer.inlineCallbacks
    @pytest.mark.usefixtures("method_tmpdir")
    def test_put_stores_on_local_db(self):
        self.manager._encrypt_and_upload = Mock(return_value=None)
        msg = "Hey Joe"
        doc = BlobDoc('mydoc_id', 'mydoc_rev', BytesIO(msg),
                      blob_id='myblob_id')
        yield self.manager.put(doc, size=len(msg))
        result = yield self.manager.local.get('myblob_id')
        self.assertEquals(result.getvalue(), msg)
        self.assertTrue(self.manager._encrypt_and_upload.called)

    @defer.inlineCallbacks
    @pytest.mark.usefixtures("method_tmpdir")
    def test_put_then_get_using_real_file_descriptor(self):
        self.manager._encrypt_and_upload = Mock(return_value=None)
        self.manager._download_and_decrypt = Mock(return_value=None)
        msg = "Fuuuuull cycleee! \o/"
        tmpfile = os.tmpfile()
        tmpfile.write(msg)
        tmpfile.seek(0)
        doc = BlobDoc('mydoc_id', 'mydoc_rev', tmpfile,
                      blob_id='myblob_id')
        yield self.manager.put(doc, size=len(msg))
        result = yield self.manager.get(doc.blob_id, doc.doc_id, doc.rev)
        self.assertEquals(result.getvalue(), msg)
        self.assertTrue(self.manager._encrypt_and_upload.called)
        self.assertFalse(self.manager._download_and_decrypt.called)

    @defer.inlineCallbacks
    @pytest.mark.usefixtures("method_tmpdir")
    def test_local_list_blobs(self):
        self.manager._encrypt_and_upload = Mock(return_value=None)
        msg = "1337"
        doc = BlobDoc('mydoc_id', 'mydoc_rev', BytesIO(msg),
                      blob_id='myblob_id')
        yield self.manager.put(doc, size=len(msg))
        doc2 = BlobDoc('mydoc_id2', 'mydoc_rev2', BytesIO(msg),
                       blob_id='myblob_id2')
        yield self.manager.put(doc2, size=len(msg))
        blobs_list = yield self.manager.local_list()

        self.assertEquals(set(['myblob_id', 'myblob_id2']), set(blobs_list))
