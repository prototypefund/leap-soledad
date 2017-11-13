# -*- coding: utf-8 -*-
# __init__.py
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
Clientside BlobBackend Storage.
"""

from urlparse import urljoin

import os
import json
import base64

from io import BytesIO

from twisted.logger import Logger
from twisted.internet import defer

import treq

from leap.soledad.common.errors import SoledadError
from leap.common.files import mkdir_p

from leap.soledad.client._crypto import DocInfo
from leap.soledad.client._crypto import InvalidBlob
from leap.soledad.client._crypto import BlobEncryptor
from leap.soledad.client._crypto import BlobDecryptor
from leap.soledad.client._crypto import EncryptionSchemeNotImplementedException
from leap.soledad.client._http import HTTPClient
from leap.soledad.client._pipes import TruncatedTailPipe
from leap.soledad.client._pipes import PreamblePipe

from .sql import SyncStatus
from .sql import SQLiteBlobBackend
from .sync import BlobsSynchronizer
from .errors import (
    BlobAlreadyExistsError, MaximumRetriesError,
    RetriableTransferError, BlobNotFoundError, InvalidFlagsError)


logger = Logger()
FIXED_REV = 'ImmutableRevision'  # Blob content is immutable


def check_http_status(code, blob_id=None, flags=None):
    if code == 404:
        raise BlobNotFoundError(blob_id)
    if code == 409:
        raise BlobAlreadyExistsError(blob_id)
    elif code == 406:
        raise InvalidFlagsError((blob_id, flags))
    elif code != 200:
        raise SoledadError("Server Error: %s" % code)


class DecrypterBuffer(object):

    def __init__(self, blob_id, secret, tag):
        self.doc_info = DocInfo(blob_id, FIXED_REV)
        self.secret = secret
        self.tag = tag
        self.preamble_pipe = PreamblePipe(self._make_decryptor)
        self.decrypter = None

    def _make_decryptor(self, preamble):
        try:
            self.decrypter = BlobDecryptor(
                self.doc_info, preamble,
                secret=self.secret,
                armor=False,
                start_stream=False,
                tag=self.tag)
            return TruncatedTailPipe(self.decrypter, tail_size=len(self.tag))
        except EncryptionSchemeNotImplementedException:
            # If we do not support the provided encryption scheme, than that's
            # something for the application using soledad to handle. This is
            # the case on asymmetrically encrypted documents on IncomingBox.
            self.raw_data = BytesIO()
            return self.raw_data

    def write(self, data):
        self.preamble_pipe.write(data)

    def close(self):
        if self.decrypter:
            real_size = self.decrypter.decrypted_content_size
            return self.decrypter.endStream(), real_size
        else:
            return self.raw_data, self.raw_data.tell()


class BlobManager(BlobsSynchronizer):
    """
    The BlobManager can list, put, get, set flags and synchronize blobs stored
    in local and remote storages.
    """
    max_decrypt_retries = 3
    concurrent_transfers_limit = 3
    concurrent_writes_limit = 100

    def __init__(
            self, local_path, remote, key, secret, user, token=None,
            cert_file=None):
        """
        Initialize the blob manager.

        :param local_path: The path for the local blobs database.
        :type local_path: str
        :param remote: The URL of the remote storage.
        :type remote: str
        :param secret: The secret used to encrypt/decrypt blobs.
        :type secret: str
        :param user: The uuid of the user.
        :type user: str
        :param token: The access token for interacting with remote storage.
        :type token: str
        :param cert_file: The path to the CA certificate file.
        :type cert_file: str
        """
        super(BlobsSynchronizer, self).__init__()
        if local_path:
            mkdir_p(os.path.dirname(local_path))
            self.local = SQLiteBlobBackend(local_path, key=key, user=user)
        self.remote = remote
        self.secret = secret
        self.user = user
        self._client = HTTPClient(user, token, cert_file)
        self.semaphore = defer.DeferredSemaphore(self.concurrent_writes_limit)

    def close(self):
        if hasattr(self, 'local') and self.local:
            return self.local.close()

    def count(self, namespace=''):
        """
        Count the number of blobs.

        :param namespace:
            Optional parameter to restrict operation to a given namespace.
        :type namespace: str
        :return: A deferred that fires with a dict parsed from the JSON
            response, which `count` key has the number of blobs as value.
            Eg.: {"count": 42}
        :rtype: twisted.internet.defer.Deferred
        """
        return self.remote_list(namespace=namespace, only_count=True)

    @defer.inlineCallbacks
    def remote_list(self, namespace='', order_by=None, deleted=False,
                    filter_flag=False, only_count=False):
        """
        List blobs from server, with filtering and ordering capabilities.

        :param namespace:
            Optional parameter to restrict operation to a given namespace.
        :type namespace: str
        :param order_by:
            Optional parameter to order results. Possible values are:
            date or +date - Ascending order (older first)
            -date - Descending order (newer first)
        :type order_by: str
        :param deleted:
            Optional paramter to return only deleted blobs.
        :type only_count: bool
        :param filter_flag:
            Optional parameter to filter listing to results containing the
            specified tag.
        :type filter_flag: leap.soledad.common.blobs.Flags
        :param only_count:
            Optional paramter to return only the number of blobs found.
        :type only_count: bool
        :return: A deferred that fires with a list parsed from the JSON
            response, holding the requested list of blobs.
            Eg.: ['blob_id1', 'blob_id2']
        :rtype: twisted.internet.defer.Deferred
        """
        uri = urljoin(self.remote, self.user + '/')
        params = {'namespace': namespace} if namespace else {}
        if order_by:
            params['order_by'] = order_by
        if deleted:
            params['deleted'] = deleted
        if filter_flag:
            params['filter_flag'] = filter_flag
        if only_count:
            params['only_count'] = only_count
        response = yield self._client.get(uri, params=params)
        check_http_status(response.code)
        defer.returnValue((yield response.json()))

    def local_list(self, namespace=''):
        return self.local.list(namespace)

    def local_list_status(self, status, namespace=''):
        return self.local.list_status(status, namespace)

    def put(self, doc, size, namespace='', local_only=False):
        """
        Put a blob in local storage and upload it to server.

        :param doc: A BlobDoc representing the blob.
        :type doc: leap.soledad.client._document.BlobDoc
        :param size: The size of the blob.
        :type size: int
        :param local_only: Avoids sync (doesn't send to server).
        :type local_only: bool
        :param namespace:
            Optional parameter to restrict operation to a given namespace.
        :type namespace: str
        """
        return self.semaphore.run(
            self._put, doc, size, namespace, local_only=local_only)

    @defer.inlineCallbacks
    def _put(self, doc, size, namespace, local_only=False):
        if (yield self.local.exists(doc.blob_id, namespace=namespace)):
            error_message = "Blob already exists: %s" % doc.blob_id
            raise BlobAlreadyExistsError(error_message)
        fd = doc.blob_fd
        # TODO this is a tee really, but ok... could do db and upload
        # concurrently. not sure if we'd gain something.
        yield self.local.put(doc.blob_id, fd, size=size, namespace=namespace)
        if local_only:
            yield self.local.update_sync_status(
                doc.blob_id, SyncStatus.LOCAL_ONLY)
            defer.returnValue(None)
        yield self.local.update_sync_status(
            doc.blob_id, SyncStatus.PENDING_UPLOAD)
        # In fact, some kind of pipe is needed here, where each write on db
        # handle gets forwarded into a write on the connection handle
        fd = yield self.local.get(doc.blob_id, namespace=namespace)
        yield self._encrypt_and_upload(doc.blob_id, fd, namespace=namespace)
        yield self.local.update_sync_status(doc.blob_id, SyncStatus.SYNCED)

    def set_flags(self, blob_id, flags, namespace=''):
        """
        Set flags for a given blob_id.

        :param blob_id:
            Unique identifier of a blob.
        :type blob_id: str
        :param flags:
            List of flags to be set.
        :type flags: [leap.soledad.common.blobs.Flags]
        :param namespace:
            Optional parameter to restrict operation to a given namespace.
        :type namespace: str
        :return: A deferred that fires when the operation finishes.
        :rtype: twisted.internet.defer.Deferred
        """
        return self.semaphore.run(self._set_flags, blob_id, flags, namespace)

    @defer.inlineCallbacks
    def _set_flags(self, blob_id, flags, namespace):
        params = {'namespace': namespace} if namespace else None
        flagsfd = BytesIO(json.dumps(flags))
        uri = urljoin(self.remote, self.user + "/" + blob_id)
        response = yield self._client.post(uri, data=flagsfd, params=params)
        check_http_status(response.code, blob_id=blob_id, flags=flags)

    @defer.inlineCallbacks
    def get_flags(self, blob_id, namespace=''):
        """
        Get flags from a given blob_id.

        :param blob_id:
            Unique identifier of a blob.
        :type blob_id: str
        :param namespace:
            Optional parameter to restrict operation to a given namespace.
        :type namespace: str
        :return: A deferred that fires with a list parsed from JSON response.
            Eg.: [Flags.PENDING]
        :rtype: twisted.internet.defer.Deferred
        """
        uri = urljoin(self.remote, self.user + "/" + blob_id)
        params = {'namespace': namespace} if namespace else {}
        params['only_flags'] = True
        response = yield self._client.get(uri, params=params)
        check_http_status(response.code, blob_id=blob_id)
        defer.returnValue((yield response.json()))

    @defer.inlineCallbacks
    def get(self, blob_id, namespace=''):
        """
        Get the blob from local storage or, if not available, from the server.

        :param blob_id:
            Unique identifier of a blob.
        :type blob_id: str
        :param namespace:
            Optional parameter to restrict operation to a given namespace.
        :type namespace: str
        """
        local_blob = yield self.local.get(blob_id, namespace=namespace)
        if local_blob:
            logger.info("Found blob in local database: %s" % blob_id)
            defer.returnValue(local_blob)

        yield self.local.update_sync_status(
            blob_id, SyncStatus.PENDING_DOWNLOAD, namespace=namespace)

        try:
            result = yield self._download_and_decrypt(blob_id, namespace)
        except Exception as e:
            _, retries = yield self.local.get_sync_status(blob_id)

            if isinstance(e, InvalidBlob):
                max_retries = self.max_decrypt_retries
                message = "Corrupted blob received from server! ID: %s\n"
                message += "Error: %r\n"
                message += "Retries: %s - Attempts left: %s\n"
                message += "This is either a bug or the contents of the "
                message += "blob have been tampered with. Please, report to "
                message += "your provider's sysadmin and submit a bug report."
                message %= (blob_id, e, retries, (max_retries - retries))
                logger.error(message)

                yield self.local.increment_retries(blob_id)

                if (retries + 1) >= max_retries:
                    failed_download = SyncStatus.FAILED_DOWNLOAD
                    yield self.local.update_sync_status(
                        blob_id, failed_download, namespace=namespace)
                    raise MaximumRetriesError(e)

            raise RetriableTransferError(e)

        if not result:
            defer.returnValue(None)
        blob, size = result

        if blob:
            logger.info("Got decrypted blob of type: %s" % type(blob))
            blob.seek(0)
            yield self.local.put(blob_id, blob, size=size, namespace=namespace)
            local_blob = yield self.local.get(blob_id, namespace=namespace)
            defer.returnValue(local_blob)
        else:
            # XXX we shouldn't get here, but we will...
            # lots of ugly error handling possible:
            # 1. retry, might be network error
            # 2. try later, maybe didn't finished streaming
            # 3.. resignation, might be error while verifying
            logger.error('sorry, dunno what happened')

    @defer.inlineCallbacks
    def _encrypt_and_upload(self, blob_id, fd, namespace=''):
        # TODO ------------------------------------------
        # this is wrong, is doing 2 stages.
        # the crypto producer can be passed to
        # the uploader and react as data is written.
        # try to rewrite as a tube: pass the fd to aes and let aes writer
        # produce data to the treq request fd.
        # ------------------------------------------------
        logger.info("Staring upload of blob: %s" % blob_id)
        doc_info = DocInfo(blob_id, FIXED_REV)
        uri = urljoin(self.remote, self.user + "/" + blob_id)
        crypter = BlobEncryptor(doc_info, fd, secret=self.secret,
                                armor=False)
        fd = yield crypter.encrypt()
        params = {'namespace': namespace} if namespace else None
        response = yield self._client.put(uri, data=fd, params=params)
        check_http_status(response.code, blob_id)
        logger.info("Finished upload: %s" % (blob_id,))

    @defer.inlineCallbacks
    def _download_and_decrypt(self, blob_id, namespace=''):
        logger.info("Staring download of blob: %s" % blob_id)
        # TODO this needs to be connected in a tube
        uri = urljoin(self.remote, self.user + '/' + blob_id)
        params = {'namespace': namespace} if namespace else None
        response = yield self._client.get(uri, params=params)
        check_http_status(response.code, blob_id=blob_id)

        if not response.headers.hasHeader('Tag'):
            msg = "Server didn't send a tag header for: %s" % blob_id
            logger.error(msg)
            raise SoledadError(msg)
        tag = response.headers.getRawHeaders('Tag')[0]
        tag = base64.urlsafe_b64decode(tag)
        buf = DecrypterBuffer(blob_id, self.secret, tag)

        # incrementally collect the body of the response
        yield treq.collect(response, buf.write)
        fd, size = buf.close()
        logger.info("Finished download: (%s, %d)" % (blob_id, size))
        defer.returnValue((fd, size))

    def delete(self, blob_id, namespace=''):
        """
        Delete a blob from local and remote storages.

        :param blob_id:
            Unique identifier of a blob.
        :type blob_id: str
        :param namespace:
            Optional parameter to restrict operation to a given namespace.
        :type namespace: str
        :return: A deferred that fires when the operation finishes.
        :rtype: twisted.internet.defer.Deferred
        """
        return self.semaphore.run(self._delete, blob_id, namespace)

    @defer.inlineCallbacks
    def _delete(self, blob_id, namespace):
        logger.info("Marking blobs as PENDING_DELETE: %s" % blob_id)
        yield self.local.update_sync_status(
            blob_id, SyncStatus.PENDING_DELETE, namespace=namespace)
        logger.info("Staring deletion of blob: %s" % blob_id)
        yield self._delete_from_remote(blob_id, namespace=namespace)
        if (yield self.local.exists(blob_id, namespace=namespace)):
            yield self.local.delete(blob_id, namespace=namespace)
        yield self.local.update_sync_status(
            blob_id, SyncStatus.SYNCED, namespace=namespace)

    @defer.inlineCallbacks
    def _delete_from_remote(self, blob_id, namespace=''):
        # TODO this needs to be connected in a tube
        uri = urljoin(self.remote, self.user + '/' + blob_id)
        params = {'namespace': namespace} if namespace else None
        response = yield self._client.delete(uri, params=params)
        check_http_status(response.code, blob_id=blob_id)
        defer.returnValue(response)
