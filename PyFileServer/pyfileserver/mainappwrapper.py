"""
mainappwrapper
==============

:Module: pyfileserver.mainappwrapper
:Author: Ho Chun Wei, fuzzybr80(at)gmail.com
:Project: PyFileServer, http://pyfilesync.berlios.de/
:Copyright: Lesser GNU Public License, see LICENSE file attached with package

See Running PyFileServer in ext_wsgiutils_server.py

"""

__docformat__ = 'reStructuredText'


import os
import sys
import atexit
import traceback

from extrequestserver import RequestServer
from processrequesterrorhandler import ErrorPrinter
from httpauthentication import HTTPAuthenticator, SimpleDomainController
from requestresolver import RequestResolver
from pyfiledomaincontroller import PyFileServerDomainController


from propertylibrary import PropertyManager
from locklibrary import LockManager
import websupportfuncs
import httpdatehelper
from pyfileserver.fileabstractionlayer import FilesystemAbstractionLayer

class PyFileApp(object):

    def __init__(self, locks_manager, props_manager,
                 domain_controller,
                 verbose=0,
                 server_info=None,
                 **servcfg):
        self._srvcfg = servcfg

        self.server_info = server_info or {}
        #add default abstraction layer
        self._srvcfg.setdefault('resAL_library', {})
        self._srvcfg.setdefault('resAL_mapping', {})
        self._srvcfg.setdefault('config_mapping', {})
        self._srvcfg['resAL_library']['*'] = FilesystemAbstractionLayer()
        
        self._infoHeader = (
            '<a href="mailto:%s">Administrator</a> at %s'
            % (self.server_info.get('admin_email', ''),
               self.server_info.get('organization', '')))
        self._verbose = verbose

        application = RequestServer(
            props_manager, locks_manager)
        application = HTTPAuthenticator(
            application, domain_controller)
        application = RequestResolver(application)      
        application = ErrorPrinter(
            application, server_descriptor=self._infoHeader) 

        self._application = application


    def __call__(self, environ, start_response):
        environ['pyfileserver.config'] = self._srvcfg
        environ['pyfileserver.trailer'] = self._infoHeader

        if self._verbose and self._verbose <= 1:
            print >> environ['wsgi.errors'], '[',httpdatehelper.getstrftime(),'] from ', environ.get('REMOTE_ADDR','unknown'), ' ', environ.get('REQUEST_METHOD','unknown'), ' ', environ.get('PATH_INFO','unknown'), ' ', environ.get('HTTP_DESTINATION', '')
        elif self._verbose > 1:
            print >> environ['wsgi.errors'], "<======== Request Environ"
            for envitem in environ.keys():
                if envitem == envitem.upper():
                    print >> environ['wsgi.errors'], "\t", envitem, ":\t", repr(environ[envitem]) 
            print >> environ['wsgi.errors'], "\n"

        def _start_response(respcode, headers, excinfo=None):   
            if self._verbose > 1:
                print >> environ['wsgi.errors'], "=========> Response"
                print >> environ['wsgi.errors'], 'Response code:', respcode
                headersdict = dict(headers)
                for envitem in headersdict.keys():
                    print >> environ['wsgi.errors'], "\t", envitem, ":\t", repr(headersdict[envitem]) 
                print >> environ['wsgi.errors'], "\n"
            return start_response(respcode, headers, excinfo)

        for v in iter(self._application(environ, _start_response)):
            if self._verbose > 1 and environ['REQUEST_METHOD'] != 'GET':
                print >> environ['wsgi.errors'], v
            yield v 

        return 
        
        
