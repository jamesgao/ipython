# encoding: utf-8
"""Facilities for handling client connections to the controller."""

#-----------------------------------------------------------------------------
#  Copyright (C) 2008-2009  The IPython Development Team
#
#  Distributed under the terms of the BSD License.  The full license is in
#  the file COPYING, distributed as part of this software.
#-----------------------------------------------------------------------------

#-----------------------------------------------------------------------------
# Imports
#-----------------------------------------------------------------------------

from __future__ import with_statement
import os

from IPython.kernel.fcutil import (
    Tub,
    find_furl,
    is_valid_furl,
    is_valid_furl_file,
    is_valid_furl_or_file,
    validate_furl_or_file,
    FURLError
)
from IPython.kernel.clusterdir import ClusterDir, ClusterDirError
from IPython.kernel.launcher import IPClusterLauncher
from IPython.kernel.twistedutil import (
    gatherBoth, 
    make_deferred,
    blockingCallFromThread, 
    sleep_deferred
)
from IPython.utils.importstring import import_item
from IPython.utils.path import get_ipython_dir

from twisted.internet import defer
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.python import failure, log

#-----------------------------------------------------------------------------
# The ClientConnector class
#-----------------------------------------------------------------------------

DELAY = 0.2
MAX_TRIES = 9


class ClientConnectorError(Exception):
    pass


class AsyncClientConnector(object):
    """A class for getting remote references and clients from furls.

    This start a single :class:`Tub` for all remote reference and caches
    references.
    """

    def __init__(self):
        self._remote_refs = {}
        self.tub = Tub()
        self.tub.startService()

    def _find_furl(self, profile='default', cluster_dir=None, 
                   furl_or_file=None, furl_file_name=None,
                   ipython_dir=None):
        """Find a FURL file.

        If successful, this returns a FURL file that exists on the file
        system. The contents of the file have not been checked though. This
        is because we often have to deal with FURL file whose buffers have
        not been flushed.

        This raises an :exc:`~IPython.kernel.fcutil.FURLError` exception 
        if a FURL file can't be found.

        This tries the following:
        
        1. By the name ``furl_or_file``.
        2. By ``cluster_dir`` and ``furl_file_name``.
        3. By cluster profile with a default of ``default``. This uses
           ``ipython_dir``.
        """
        # Try by furl_or_file
        if furl_or_file is not None:
            if is_valid_furl_or_file(furl_or_file):
                return furl_or_file

        if furl_file_name is None:
            raise FURLError('A furl_file_name must be provided if furl_or_file is not')

        # Try by cluster_dir
        if cluster_dir is not None:
            cluster_dir_obj = ClusterDir.find_cluster_dir(cluster_dir)
            sdir = cluster_dir_obj.security_dir
            furl_file = os.path.join(sdir, furl_file_name)
            validate_furl_or_file(furl_file)
            return furl_file

        # Try by profile
        if ipython_dir is None:
            ipython_dir = get_ipython_dir()
        if profile is not None:
            cluster_dir_obj = ClusterDir.find_cluster_dir_by_profile(
                ipython_dir, profile)
            sdir = cluster_dir_obj.security_dir
            furl_file = os.path.join(sdir, furl_file_name)
            validate_furl_or_file(furl_file)
            return furl_file

        raise FURLError('Could not find a valid FURL file.')

    def get_reference(self, furl_or_file):
        """Get a remote reference using a furl or a file containing a furl.

        Remote references are cached locally so once a remote reference
        has been retrieved for a given furl, the cached version is 
        returned.

        Parameters
        ----------
        furl_or_file : str
            A furl or a filename containing a furl. This should already be
            validated, but might not yet exist.

        Returns
        -------
        A deferred to a remote reference
        """
        furl = furl_or_file
        if furl in self._remote_refs:
            d = defer.succeed(self._remote_refs[furl])
        else:
            d = self.tub.getReference(furl)
            d.addCallback(self._save_ref, furl)
        return d
        
    def _save_ref(self, ref, furl):
        """Cache a remote reference by its furl."""
        self._remote_refs[furl] = ref
        return ref
        
    def get_task_client(self, profile='default', cluster_dir=None,
                        furl_or_file=None, ipython_dir=None,
                        delay=DELAY, max_tries=MAX_TRIES):
        """Get the task controller client.
        
        This method is a simple wrapper around `get_client` that passes in
        the default name of the task client FURL file.  Usually only
        the ``profile`` option will be needed.  If a FURL file can't be
        found by its profile, use ``cluster_dir`` or ``furl_or_file``.
        
        Parameters
        ----------
        profile : str
            The name of a cluster directory profile (default="default"). The
            cluster directory "cluster_<profile>" will be searched for
            in ``os.getcwd()``, the ipython_dir and then in the directories
            listed in the :env:`IPCLUSTER_DIR_PATH` environment variable.
        cluster_dir : str
            The full path to a cluster directory.  This is useful if profiles
            are not being used.
        furl_or_file : str
            A furl or a filename containing a FURL. This is useful if you 
            simply know the location of the FURL file.
        ipython_dir : str
            The location of the ipython_dir if different from the default.
            This is used if the cluster directory is being found by profile.
        delay : float
            The initial delay between re-connection attempts. Susequent delays
            get longer according to ``delay[i] = 1.5*delay[i-1]``.
        max_tries : int
            The max number of re-connection attempts.

        Returns
        -------
        A deferred to the actual client class.
        """
        return self.get_client(
            profile, cluster_dir, furl_or_file, 
            'ipcontroller-tc.furl', ipython_dir,
            delay, max_tries
        )

    def get_multiengine_client(self, profile='default', cluster_dir=None,
                               furl_or_file=None, ipython_dir=None,
                               delay=DELAY, max_tries=MAX_TRIES):
        """Get the multiengine controller client.
        
        This method is a simple wrapper around `get_client` that passes in
        the default name of the task client FURL file.  Usually only
        the ``profile`` option will be needed.  If a FURL file can't be
        found by its profile, use ``cluster_dir`` or ``furl_or_file``.
        
        Parameters
        ----------
        profile : str
            The name of a cluster directory profile (default="default"). The
            cluster directory "cluster_<profile>" will be searched for
            in ``os.getcwd()``, the ipython_dir and then in the directories
            listed in the :env:`IPCLUSTER_DIR_PATH` environment variable.
        cluster_dir : str
            The full path to a cluster directory.  This is useful if profiles
            are not being used.
        furl_or_file : str
            A furl or a filename containing a FURL. This is useful if you 
            simply know the location of the FURL file.
        ipython_dir : str
            The location of the ipython_dir if different from the default.
            This is used if the cluster directory is being found by profile.
        delay : float
            The initial delay between re-connection attempts. Susequent delays
            get longer according to ``delay[i] = 1.5*delay[i-1]``.
        max_tries : int
            The max number of re-connection attempts.

        Returns
        -------
        A deferred to the actual client class.
        """
        return self.get_client(
            profile, cluster_dir, furl_or_file, 
            'ipcontroller-mec.furl', ipython_dir,
            delay, max_tries
        )
    
    def get_client(self, profile='default', cluster_dir=None,
                   furl_or_file=None, furl_file_name=None, ipython_dir=None,
                   delay=DELAY, max_tries=MAX_TRIES):
        """Get a remote reference and wrap it in a client by furl.

        This method is a simple wrapper around `get_client` that passes in
        the default name of the task client FURL file.  Usually only
        the ``profile`` option will be needed.  If a FURL file can't be
        found by its profile, use ``cluster_dir`` or ``furl_or_file``.
        
        Parameters
        ----------
        profile : str
            The name of a cluster directory profile (default="default"). The
            cluster directory "cluster_<profile>" will be searched for
            in ``os.getcwd()``, the ipython_dir and then in the directories
            listed in the :env:`IPCLUSTER_DIR_PATH` environment variable.
        cluster_dir : str
            The full path to a cluster directory.  This is useful if profiles
            are not being used.
        furl_or_file : str
            A furl or a filename containing a FURL. This is useful if you 
            simply know the location of the FURL file.
        furl_file_name : str
            The filename (not the full path) of the FURL. This must be
            provided if ``furl_or_file`` is not.
        ipython_dir : str
            The location of the ipython_dir if different from the default.
            This is used if the cluster directory is being found by profile.
        delay : float
            The initial delay between re-connection attempts. Susequent delays
            get longer according to ``delay[i] = 1.5*delay[i-1]``.
        max_tries : int
            The max number of re-connection attempts.

        Returns
        -------
        A deferred to the actual client class. Or a failure to a 
        :exc:`FURLError`.
        """
        try:
            furl_file = self._find_furl(
                profile, cluster_dir, furl_or_file,
                furl_file_name, ipython_dir
            )
            # If this succeeds, we know the furl file exists and has a .furl
            # extension, but it could still be empty. That is checked each
            # connection attempt.
        except FURLError:
            return defer.fail(failure.Failure())

        def _wrap_remote_reference(rr):
            d = rr.callRemote('get_client_name')
            d.addCallback(lambda name: import_item(name))
            def adapt(client_interface):
                client = client_interface(rr)
                client.tub = self.tub
                return client
            d.addCallback(adapt)

            return d

        d = self._try_to_connect(furl_file, delay, max_tries, attempt=0)
        d.addCallback(_wrap_remote_reference)
        d.addErrback(self._handle_error, furl_file)
        return d

    def _handle_error(self, f, furl_file):
        raise ClientConnectorError('Could not connect to the controller '
            'using the FURL file. This usually means that i) the controller '
            'was not started or ii) a firewall was blocking the client from '
            'connecting to the controller: %s' % furl_file)

    @inlineCallbacks
    def _try_to_connect(self, furl_or_file, delay, max_tries, attempt):
        """Try to connect to the controller with retry logic."""
        if attempt < max_tries:
            log.msg("Connecting [%r]" % attempt)
            try:
                self.furl = find_furl(furl_or_file)
                # Uncomment this to see the FURL being tried.
                # log.msg("FURL: %s" % self.furl)
                rr = yield self.get_reference(self.furl)
                log.msg("Connected: %s" % furl_or_file)
            except:
                if attempt==max_tries-1:
                    # This will propagate the exception all the way to the top
                    # where it can be handled.
                    raise
                else:
                    yield sleep_deferred(delay)
                    rr = yield self._try_to_connect(
                        furl_or_file, 1.5*delay, max_tries, attempt+1
                    )
                    returnValue(rr)
            else:
                returnValue(rr)
        else:
            raise ClientConnectorError(
                'Could not connect to controller, max_tries (%r) exceeded. '
                'This usually means that i) the controller was not started, '
                'or ii) a firewall was blocking the client from connecting '
                'to the controller.' % max_tries
            )


class ClientConnector(object):
    """A blocking version of a client connector.

    This class creates a single :class:`Tub` instance and allows remote
    references and client to be retrieved by their FURLs.  Remote references
    are cached locally and FURL files can be found using profiles and cluster
    directories.
    """

    def __init__(self):
        self.async_cc = AsyncClientConnector()

    def get_task_client(self, profile='default', cluster_dir=None,
                        furl_or_file=None, ipython_dir=None,
                        delay=DELAY, max_tries=MAX_TRIES):
        """Get the task client.
        
        Usually only the ``profile`` option will be needed. If a FURL file
        can't be found by its profile, use ``cluster_dir`` or
        ``furl_or_file``.
        
        Parameters
        ----------
        profile : str
            The name of a cluster directory profile (default="default"). The
            cluster directory "cluster_<profile>" will be searched for
            in ``os.getcwd()``, the ipython_dir and then in the directories
            listed in the :env:`IPCLUSTER_DIR_PATH` environment variable.
        cluster_dir : str
            The full path to a cluster directory.  This is useful if profiles
            are not being used.
        furl_or_file : str
            A furl or a filename containing a FURL. This is useful if you 
            simply know the location of the FURL file.
        ipython_dir : str
            The location of the ipython_dir if different from the default.
            This is used if the cluster directory is being found by profile.
        delay : float
            The initial delay between re-connection attempts. Susequent delays
            get longer according to ``delay[i] = 1.5*delay[i-1]``.
        max_tries : int
            The max number of re-connection attempts.

        Returns
        -------
        The task client instance.
        """
        client = blockingCallFromThread(
            self.async_cc.get_task_client, profile, cluster_dir,
            furl_or_file, ipython_dir, delay, max_tries
        )
        return client.adapt_to_blocking_client()

    def get_multiengine_client(self, profile='default', cluster_dir=None,
                               furl_or_file=None, ipython_dir=None,
                               delay=DELAY, max_tries=MAX_TRIES):
        """Get the multiengine client.
        
        Usually only the ``profile`` option will be needed. If a FURL file
        can't be found by its profile, use ``cluster_dir`` or
        ``furl_or_file``.
        
        Parameters
        ----------
        profile : str
            The name of a cluster directory profile (default="default"). The
            cluster directory "cluster_<profile>" will be searched for
            in ``os.getcwd()``, the ipython_dir and then in the directories
            listed in the :env:`IPCLUSTER_DIR_PATH` environment variable.
        cluster_dir : str
            The full path to a cluster directory.  This is useful if profiles
            are not being used.
        furl_or_file : str
            A furl or a filename containing a FURL. This is useful if you 
            simply know the location of the FURL file.
        ipython_dir : str
            The location of the ipython_dir if different from the default.
            This is used if the cluster directory is being found by profile.
        delay : float
            The initial delay between re-connection attempts. Susequent delays
            get longer according to ``delay[i] = 1.5*delay[i-1]``.
        max_tries : int
            The max number of re-connection attempts.

        Returns
        -------
        The multiengine client instance.
        """
        client = blockingCallFromThread(
            self.async_cc.get_multiengine_client, profile, cluster_dir,
            furl_or_file, ipython_dir, delay, max_tries
        )
        return client.adapt_to_blocking_client()

    def get_client(self, profile='default', cluster_dir=None,
                   furl_or_file=None, ipython_dir=None,
                   delay=DELAY, max_tries=MAX_TRIES):
        client = blockingCallFromThread(
            self.async_cc.get_client, profile, cluster_dir,
            furl_or_file, ipython_dir,
            delay, max_tries
        )
        return client.adapt_to_blocking_client()


class ClusterStateError(Exception):
    pass


class AsyncCluster(object):
    """An class that wraps the :command:`ipcluster` script."""

    def __init__(self, profile='default', cluster_dir=None, ipython_dir=None,
                 auto_create=False, auto_stop=True):
        """Create a class to manage an IPython cluster.

        This class calls the :command:`ipcluster` command with the right
        options to start an IPython cluster.  Typically a cluster directory
        must be created (:command:`ipcluster create`) and configured before 
        using this class. Configuration is done by editing the 
        configuration files in the top level of the cluster directory.

        Parameters
        ----------
        profile : str
            The name of a cluster directory profile (default="default"). The
            cluster directory "cluster_<profile>" will be searched for
            in ``os.getcwd()``, the ipython_dir and then in the directories
            listed in the :env:`IPCLUSTER_DIR_PATH` environment variable.
        cluster_dir : str
            The full path to a cluster directory.  This is useful if profiles
            are not being used.
        ipython_dir : str
            The location of the ipython_dir if different from the default.
            This is used if the cluster directory is being found by profile.
        auto_create : bool
            Automatically create the cluster directory it is dones't exist.
            This will usually only make sense if using a local cluster 
            (default=False).
        auto_stop : bool
            Automatically stop the cluster when this instance is garbage 
            collected (default=True).  This is useful if you want the cluster
            to live beyond your current process. There is also an instance
            attribute ``auto_stop`` to change this behavior.
        """
        self._setup_cluster_dir(profile, cluster_dir, ipython_dir, auto_create)
        self.state = 'before'
        self.launcher = None
        self.client_connector = None
        self.auto_stop = auto_stop

    def __del__(self):
        if self.auto_stop and self.state=='running':
            print "Auto stopping the cluster..."
            self.stop()

    @property
    def location(self):
        if hasattr(self, 'cluster_dir_obj'):
            return self.cluster_dir_obj.location
        else:
            return ''

    @property
    def running(self):
        if self.state=='running':
            return True
        else:
            return False

    def _setup_cluster_dir(self, profile, cluster_dir, ipython_dir, auto_create):
        if ipython_dir is None:
            ipython_dir = get_ipython_dir()
        if cluster_dir is not None:
            try:
                self.cluster_dir_obj = ClusterDir.find_cluster_dir(cluster_dir)
            except ClusterDirError:
                pass
        if profile is not None:
            try:
                self.cluster_dir_obj = ClusterDir.find_cluster_dir_by_profile(
                    ipython_dir, profile)
            except ClusterDirError:
                pass
        if auto_create or profile=='default':
            # This should call 'ipcluster create --profile default
            self.cluster_dir_obj = ClusterDir.create_cluster_dir_by_profile(
                ipython_dir, profile)
        else:
            raise ClusterDirError('Cluster dir not found.')

    @make_deferred
    def start(self, n=2):
        """Start the IPython cluster with n engines.

        Parameters
        ----------
        n : int
            The number of engine to start.
        """
        # We might want to add logic to test if the cluster has started
        # by another process....
        if not self.state=='running':
            self.launcher = IPClusterLauncher(os.getcwd())
            self.launcher.ipcluster_n = n
            self.launcher.ipcluster_subcommand = 'start'
            d = self.launcher.start()
            d.addCallback(self._handle_start)
            return d
        else:
            raise ClusterStateError('Cluster is already running')

    @make_deferred
    def stop(self):
        """Stop the IPython cluster if it is running."""
        if self.state=='running':
            d1 = self.launcher.observe_stop()
            d1.addCallback(self._handle_stop)
            d2 = self.launcher.stop()
            return gatherBoth([d1, d2], consumeErrors=True)
        else:
            raise ClusterStateError("Cluster not running")

    def get_multiengine_client(self, delay=DELAY, max_tries=MAX_TRIES):
        """Get the multiengine client for the running cluster.

        If this fails, it means that the cluster has not finished starting.
        Usually waiting a few seconds are re-trying will solve this.    
        """
        if self.client_connector is None:
            self.client_connector = AsyncClientConnector()
        return self.client_connector.get_multiengine_client(
            cluster_dir=self.cluster_dir_obj.location,
            delay=delay, max_tries=max_tries
        )

    def get_task_client(self, delay=DELAY, max_tries=MAX_TRIES):
        """Get the task client for the running cluster.

        If this fails, it means that the cluster has not finished starting.
        Usually waiting a few seconds are re-trying will solve this.    
        """
        if self.client_connector is None:
            self.client_connector = AsyncClientConnector()
        return self.client_connector.get_task_client(
            cluster_dir=self.cluster_dir_obj.location,
            delay=delay, max_tries=max_tries
        )

    def get_ipengine_logs(self):
        return self.get_logs_by_name('ipengine')

    def get_ipcontroller_logs(self):
        return self.get_logs_by_name('ipcontroller')

    def get_ipcluster_logs(self):
        return self.get_logs_by_name('ipcluster')

    def get_logs_by_name(self, name='ipcluster'):
        log_dir = self.cluster_dir_obj.log_dir
        logs = {}
        for log in os.listdir(log_dir):
            if log.startswith(name + '-') and log.endswith('.log'):
                with open(os.path.join(log_dir, log), 'r') as f:
                    logs[log] = f.read()
        return logs

    def get_logs(self):
        d = self.get_ipcluster_logs()
        d.update(self.get_ipengine_logs())
        d.update(self.get_ipcontroller_logs())
        return d

    def _handle_start(self, r):
        self.state = 'running'

    def _handle_stop(self, r):
        self.state = 'after'


class Cluster(object):


    def __init__(self, profile='default', cluster_dir=None, ipython_dir=None,
                 auto_create=False, auto_stop=True):
        """Create a class to manage an IPython cluster.

        This class calls the :command:`ipcluster` command with the right
        options to start an IPython cluster.  Typically a cluster directory
        must be created (:command:`ipcluster create`) and configured before 
        using this class. Configuration is done by editing the 
        configuration files in the top level of the cluster directory.

        Parameters
        ----------
        profile : str
            The name of a cluster directory profile (default="default"). The
            cluster directory "cluster_<profile>" will be searched for
            in ``os.getcwd()``, the ipython_dir and then in the directories
            listed in the :env:`IPCLUSTER_DIR_PATH` environment variable.
        cluster_dir : str
            The full path to a cluster directory.  This is useful if profiles
            are not being used.
        ipython_dir : str
            The location of the ipython_dir if different from the default.
            This is used if the cluster directory is being found by profile.
        auto_create : bool
            Automatically create the cluster directory it is dones't exist.
            This will usually only make sense if using a local cluster 
            (default=False).
        auto_stop : bool
            Automatically stop the cluster when this instance is garbage 
            collected (default=True).  This is useful if you want the cluster
            to live beyond your current process. There is also an instance
            attribute ``auto_stop`` to change this behavior.
        """
        self.async_cluster = AsyncCluster(
            profile, cluster_dir, ipython_dir, auto_create, auto_stop
        )
        self.cluster_dir_obj = self.async_cluster.cluster_dir_obj
        self.client_connector = None

    def _set_auto_stop(self, value):
        self.async_cluster.auto_stop = value

    def _get_auto_stop(self):
        return self.async_cluster.auto_stop

    auto_stop = property(_get_auto_stop, _set_auto_stop)

    @property
    def location(self):
        return self.async_cluster.location

    @property
    def running(self):
        return self.async_cluster.running

    def start(self, n=2):
        """Start the IPython cluster with n engines.

        Parameters
        ----------
        n : int
            The number of engine to start.
        """
        return blockingCallFromThread(self.async_cluster.start, n)

    def stop(self):
        """Stop the IPython cluster if it is running."""
        return blockingCallFromThread(self.async_cluster.stop)

    def get_multiengine_client(self, delay=DELAY, max_tries=MAX_TRIES):
        """Get the multiengine client for the running cluster.

        This will try to attempt to the controller multiple times. If this 
        fails altogether, try looking at the following:
        * Make sure the controller is starting properly by looking at its
          log files.
        * Make sure the controller is writing its FURL file in the location
          expected by the client.
        * Make sure a firewall on the controller's host is not blocking the
          client from connecting.

        Parameters
        ----------
        delay : float
            The initial delay between re-connection attempts. Susequent delays
            get longer according to ``delay[i] = 1.5*delay[i-1]``.
        max_tries : int
            The max number of re-connection attempts.
        """
        if self.client_connector is None:
            self.client_connector = ClientConnector()
        return self.client_connector.get_multiengine_client(
            cluster_dir=self.cluster_dir_obj.location,
            delay=delay, max_tries=max_tries
        )

    def get_task_client(self, delay=DELAY, max_tries=MAX_TRIES):
        """Get the task client for the running cluster.

        This will try to attempt to the controller multiple times. If this 
        fails altogether, try looking at the following:
        * Make sure the controller is starting properly by looking at its
          log files.
        * Make sure the controller is writing its FURL file in the location
          expected by the client.
        * Make sure a firewall on the controller's host is not blocking the
          client from connecting.

        Parameters
        ----------
        delay : float
            The initial delay between re-connection attempts. Susequent delays
            get longer according to ``delay[i] = 1.5*delay[i-1]``.
        max_tries : int
            The max number of re-connection attempts.
        """
        if self.client_connector is None:
            self.client_connector = ClientConnector()
        return self.client_connector.get_task_client(
            cluster_dir=self.cluster_dir_obj.location,
            delay=delay, max_tries=max_tries
        )

    def __repr__(self):
        s = "<Cluster(running=%r, location=%s)" % (self.running, self.location)
        return s

    def get_logs_by_name(self, name='ipcluter'):
        """Get a dict of logs by process name (ipcluster, ipengine, etc.)"""
        return self.async_cluster.get_logs_by_name(name)

    def get_ipengine_logs(self):
        """Get a dict of logs for all engines in this cluster."""
        return self.async_cluster.get_ipengine_logs()

    def get_ipcontroller_logs(self):
        """Get a dict of logs for the controller in this cluster."""
        return self.async_cluster.get_ipcontroller_logs()

    def get_ipcluster_logs(self):
        """Get a dict of the ipcluster logs for this cluster."""
        return self.async_cluster.get_ipcluster_logs()

    def get_logs(self):
        """Get a dict of all logs for this cluster."""
        return self.async_cluster.get_logs()

    def _print_logs(self, logs):
        for k, v in logs.iteritems():
            print "==================================="
            print "Logfile: %s" % k
            print "==================================="
            print v
            print

    def print_ipengine_logs(self):
        """Print the ipengine logs for this cluster to stdout."""
        self._print_logs(self.get_ipengine_logs())

    def print_ipcontroller_logs(self):
        """Print the ipcontroller logs for this cluster to stdout."""
        self._print_logs(self.get_ipcontroller_logs())

    def print_ipcluster_logs(self):
        """Print the ipcluster logs for this cluster to stdout."""
        self._print_logs(self.get_ipcluster_logs())

    def print_logs(self):
        """Print all the logs for this cluster to stdout."""
        self._print_logs(self.get_logs())

