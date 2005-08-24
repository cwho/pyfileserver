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

import etagprovider
from extrequestserver import RequestServer
from processrequesterrorhandler import ErrorPrinter
from httpauthentication import HTTPAuthenticator, SimpleDomainController
from requestresolver import RequestResolver
from pyfiledomaincontroller import PyFileServerDomainController
from propertylibrary import PropertyManager
from propertylibrary import LockManager
import websupportfuncs
import httpdatehelper

class PyFileApp(object):

    def __init__(self, specifiedconfigfile = None):

        if specifiedconfigfile == None:
            specifiedconfigfile = os.getcwd() + os.sep + 'PyFileServer.conf'

        loadconfig = True
        try:      
            from paste import pyconfig
            servcfg = pyconfig.Config()
            servcfg.load(specifiedconfigfile)
        except ImportError:         
            try:
                import loadconfig_primitive
                servcfg = loadconfig_primitive.load(specifiedconfigfile)
            except:
                exceptioninfo = traceback.format_exception_only(sys.exc_type, sys.exc_value)
                exceptiontext = ''
                for einfo in exceptioninfo:
                    exceptiontext = exceptiontext + einfo + '\n'   
                raise RuntimeError('Failed to read PyFileServer configuration file : ' + specifiedconfigfile + '\nDue to ' + exceptiontext)
        except:
            exceptioninfo = traceback.format_exc_exception_only(sys.exc_type, sys.exc_value)
            exceptiontext = ''
            for einfo in exceptioninfo:
                exceptiontext = exceptiontext + einfo + '\n'   
            raise RuntimeError('Failed to read PyFileServer configuration file : ' + specifiedconfigfile + '\nDue to ' + exceptiontext)


        self._srvcfg = servcfg
        self._infoHeader = '<A href=\"mailto:' + servcfg.get('Info_AdminEmail','') + '\">Administrator</A> at ' + servcfg.get('Info_Organization','')

        self._verbose = servcfg.get('verbose', 0)

        # file locations

        _locksmanagerobj = servcfg.get('locksmanager', None)
        _propsmanagerobj = servcfg.get('propsmanager', None)      
        _etagproviderfuncobj = servcfg.get('etagproviderfunction', None)

        _domaincontrollerobj = servcfg.get('domaincontroller', None)

        _locksfile = servcfg.get('locksfile', os.getcwd() + os.sep + 'PyFileServer.locks')
        _propsfile = servcfg.get('propsfile', os.getcwd() + os.sep + 'PyFileServer.dat')

        if _propsmanagerobj == None:
            _propsmanagerobj = PropertyManager(_propsfile)

        if _locksmanagerobj == None:
            _locksmanagerobj = LockManager(_locksfile)

        if _etagproviderfuncobj == None:
            _etagproviderfuncobj = etagprovider.getETag   

        if _domaincontrollerobj == None:   
            _domaincontrollerobj = PyFileServerDomainController()

        # authentication fields
        _authacceptbasic = servcfg.get('acceptbasic', False)
        _authacceptdigest = servcfg.get('acceptdigest', True)
        _authdefaultdigest = servcfg.get('defaultdigest', True)

        application = RequestServer(_propsmanagerobj, _locksmanagerobj, _etagproviderfuncobj)      
        application = HTTPAuthenticator(application, _domaincontrollerobj, _authacceptbasic, _authacceptdigest, _authdefaultdigest)      
        application = RequestResolver(application)      
        application = ErrorPrinter(application, server_descriptor=self._infoHeader) 

        self._application = application


    def __call__(self, environ, start_response):
        environ['pyfileserver.config'] = self._srvcfg
        environ['pyfileserver.trailer'] = self._infoHeader

        if self._verbose == 1:
            print '[',httpdatehelper.getstrftime(),'] from ', environ.get('REMOTE_ADDR','unknown'), ' ', environ.get('REQUEST_METHOD','unknown'), ' ', environ.get('PATH_INFO','unknown'), ' ', environ.get('HTTP_DESTINATION', '')
        elif self._verbose == 2:      
            print "<======== Request Environ"
            for envitem in environ.keys():
                if envitem == envitem.upper():
                    print "\t", envitem, ":\t", repr(environ[envitem]) 
            print "\n"

        def _start_response(respcode, headers, excinfo=None):   
            if self._verbose == 2:
                print "=========> Response"
                print 'Response code:', respcode
                headersdict = dict(headers)
                for envitem in headersdict.keys():
                    print "\t", envitem, ":\t", repr(headersdict[envitem]) 
                print "\n"
            return start_response(respcode, headers, excinfo)

        for v in iter(self._application(environ, _start_response)):
            if self._verbose == 2 and environ['REQUEST_METHOD'] != 'GET':
                print v
            yield v 

        return 

