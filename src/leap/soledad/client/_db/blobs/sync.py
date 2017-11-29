# -*- coding: utf-8 -*-
# sync.py
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
Synchronization between blobs client/server
"""
from collections import defaultdict
from twisted.internet import defer
from twisted.internet import reactor
from twisted.logger import Logger
from twisted.internet import error
from .sql import SyncStatus
from .errors import RetriableTransferError


logger = Logger()


def sleep(seconds):
    d = defer.Deferred()
    reactor.callLater(seconds, d.callback, None)
    return d


MAX_WAIT = 60  # In seconds. Max time between retries


@defer.inlineCallbacks
def with_retry(func, *args, **kwargs):
    """
    Run func repeatedly until success, as long as the exception raised is
    a "retriable error". If an exception of another kind is raised by func,
    the retrying stops and that exception is propagated up the stack.
    """
    retry_wait = 1
    retriable_errors = (error.ConnectError, error.ConnectionClosed,
                        RetriableTransferError,)
    while True:
        try:
            yield func(*args, **kwargs)
            break
        except retriable_errors:
            yield sleep(retry_wait)
            retry_wait = min(retry_wait + 10, MAX_WAIT)


class BlobsSynchronizer(object):

    def __init__(self):
        self.locks = defaultdict(defer.DeferredLock)

    @defer.inlineCallbacks
    def refresh_sync_status_from_server(self, namespace=''):
        d1 = self.remote_list(namespace=namespace)
        d2 = self.local_list(namespace=namespace)
        remote_list, local_list = yield defer.gatherResults([d1, d2])
        pending_download_ids = tuple(set(remote_list) - set(local_list))
        pending_upload_ids = tuple(set(local_list) - set(remote_list))
        yield self.local.update_batch_sync_status(
            pending_download_ids,
            SyncStatus.PENDING_DOWNLOAD,
            namespace=namespace)
        yield self.local.update_batch_sync_status(
            pending_upload_ids,
            SyncStatus.PENDING_UPLOAD,
            namespace=namespace)

    @defer.inlineCallbacks
    def _apply_deletions_from_server(self, namespace=''):
        remote_deletions = self.remote_list(namespace=namespace, deleted=True)
        remote_deletions = yield remote_deletions
        yield self.local.batch_delete(remote_deletions)
        yield self.local.update_batch_sync_status(
            remote_deletions,
            SyncStatus.SYNCED,
            namespace=namespace)

    def send_missing(self, namespace=''):
        """
        Compare local and remote blobs and send what's missing in server.

        :param namespace:
            Optional parameter to restrict operation to a given namespace.
        :type namespace: str

        :return: A deferred that fires when all local blobs were sent to
                 server.
        :rtype: twisted.internet.defer.Deferred
        """
        lock = self.locks['send_missing']
        d = lock.run(self._send_missing, namespace)
        return d

    @defer.inlineCallbacks
    def _send_missing(self, namespace):
        max_transfers = self.concurrent_transfers_limit
        semaphore = defer.DeferredSemaphore(max_transfers)
        # the list of blobs should be refreshed often, so we run as many
        # concurrent transfers as we can and then refresh the list
        while True:
            d = self.local_list_status(SyncStatus.PENDING_UPLOAD, namespace)
            missing = yield d

            if not missing:
                break

            total = len(missing)
            now = min(total, max_transfers)
            logger.info("There are %d pending blob uploads." % total)
            logger.info("Will send %d blobs to server now." % now)
            missing = missing[:now]
            deferreds = []
            for i in xrange(now):
                blob_id = missing.pop(0)
                d = semaphore.run(
                    with_retry, self._send, blob_id, namespace, i, total)
                deferreds.append(d)
            yield defer.gatherResults(deferreds, consumeErrors=True)

    def fetch_missing(self, namespace=''):
        """
        Compare local and remote blobs and fetch what's missing in local
        storage.

        :param namespace:
            Optional parameter to restrict operation to a given namespace.
        :type namespace: str

        :return: A deferred that fires when all remote blobs were received from
                 server.
        :rtype: twisted.internet.defer.Deferred
        """
        lock = self.locks['fetch_missing']
        d = lock.run(self._fetch_missing, namespace)
        return d

    @defer.inlineCallbacks
    def _fetch_missing(self, namespace=''):
        max_transfers = self.concurrent_transfers_limit
        semaphore = defer.DeferredSemaphore(max_transfers)
        # in order to make sure that transfer priorities will be met, the list
        # of blobs to transfer should be refreshed often. What we do is run as
        # many concurrent transfers as we can and then refresh the list
        while True:
            d = self.local_list_status(SyncStatus.PENDING_DOWNLOAD, namespace)
            docs_we_want = yield d

            if not docs_we_want:
                break

            total = len(docs_we_want)
            now = min(total, max_transfers)
            logger.info("There are %d pending blob downloads." % total)
            logger.info("Will fetch %d blobs from server now." % now)
            docs_we_want = docs_we_want[:now]
            deferreds = []
            for i in xrange(now):
                blob_id = docs_we_want.pop(0)
                logger.info("Fetching blob (%d/%d): %s" % (i, now, blob_id))
                d = semaphore.run(with_retry, self._fetch, blob_id, namespace)
                deferreds.append(d)
            yield defer.gatherResults(deferreds, consumeErrors=True)

    @defer.inlineCallbacks
    def sync(self, namespace=''):
        try:
            yield self._apply_deletions_from_server(namespace)
            yield self.refresh_sync_status_from_server(namespace)
            yield self.fetch_missing(namespace)
            yield self.send_missing(namespace)
        except defer.FirstError as e:
            e.subFailure.raiseException()

    @property
    def sync_progress(self):
        return self.local.get_sync_progress()
