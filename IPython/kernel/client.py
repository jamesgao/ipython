#!/usr/bin/env python
# encoding: utf-8

"""This module contains blocking clients for the controller interfaces.

Unlike the clients in `asyncclient.py`, the clients in this module are fully
blocking.  This means that methods on the clients return the actual results
rather than a deferred to the result.  Also, we manage the Twisted reactor
for you.  This is done by running the reactor in a thread.

The main classes in this module are:

    * MultiEngineClient
    * TaskClient
    * Task
    * CompositeError
"""

#-----------------------------------------------------------------------------
#  Copyright (C) 2008-2009  The IPython Development Team
#
#  Distributed under the terms of the BSD License.  The full license is in
#  the file COPYING, distributed as part of this software.
#-----------------------------------------------------------------------------

#-----------------------------------------------------------------------------
# Warnings control
#-----------------------------------------------------------------------------

import warnings

# Twisted generates annoying warnings with Python 2.6, as will do other code
# that imports 'sets' as of today
warnings.filterwarnings('ignore', 'the sets module is deprecated',
                        DeprecationWarning )

# This one also comes from Twisted
warnings.filterwarnings('ignore', 'the sha module is deprecated',
                        DeprecationWarning)

#-----------------------------------------------------------------------------
# Imports
#-----------------------------------------------------------------------------

import sys

from twisted.internet import reactor
from twisted.internet.error import PotentialZombieWarning
from twisted.python import log

from IPython.kernel.clientconnector import ClientConnector, Cluster
from IPython.kernel.twistedutil import ReactorInThread
from IPython.kernel.twistedutil import blockingCallFromThread

# These enable various things 
from IPython.kernel import codeutil
# import IPython.kernel.magic

# Other things that the user will need
from IPython.kernel.task import MapTask, StringTask
from IPython.kernel.error import CompositeError

#-------------------------------------------------------------------------------
# Code
#-------------------------------------------------------------------------------

warnings.simplefilter('ignore', PotentialZombieWarning)

_client_tub = ClientConnector()

get_multiengine_client = _client_tub.get_multiengine_client
get_task_client = _client_tub.get_task_client
MultiEngineClient = get_multiengine_client
TaskClient = get_task_client

# This isn't great.  I should probably set this up in the ReactorInThread
# class below.  But, it does work for now.
log.startLogging(sys.stdout, setStdout=0)

# Now we start the reactor in a thread
rit = ReactorInThread()
rit.setDaemon(True)
rit.start()


__all__ = [
    'MapTask',
    'StringTask',
    'MultiEngineClient',
    'TaskClient',
    'CompositeError',
    'get_task_client',
    'get_multiengine_client',
    'Cluster'
]
