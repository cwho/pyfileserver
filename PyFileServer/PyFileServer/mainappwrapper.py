import os
import atexit

from extrequestserver import RequestServer
from processrequesterrorhandler import ErrorPrinter
from httpauthentication import HTTPAuthenticator, SimpleDomainController
from requestresolver import RequestResolver
from pyfiledomaincontroller import PyFileServerDomainController
from propertylibrary import PropertyManager

import websupportfuncs
from paste import pyconfig

"""
Main application executable. 

Links request server with the other middleware portions
"""

class PyFileApp(object):
   
   def __init__(self):
      servcfg = pyconfig.Config()
      servcfg.load(os.getcwd() + os.sep + 'PyFileServer.conf')
      
      self._srvcfg = servcfg
      self._infoHeader = '<A href=\"mailto:' + self._srvcfg['Info_AdminEmail'] + '\">Administrator</A> at ' + self._srvcfg['Info_Organization']
      
      application = RequestServer(PropertyManager(os.getcwd() + os.sep + 'PyFileServer.dat'))      
      application = HTTPAuthenticator(application, PyFileServerDomainController(servcfg), True, True, True)      
      application = RequestResolver(application)      
      application = ErrorPrinter(application, self._infoHeader) 
      
      self._application = application

 
   def __call__(self, environ, start_response):
      environ['pyfileserver.config'] = self._srvcfg
      environ['pyfileserver.trailer'] = self._infoHeader

      print "---------------------------------------------"
#      # for debugging purposes
      for envitem in environ.keys():
         if envitem == envitem.upper() and envitem.startswith('HTTP'):
            print "\t", envitem, ":\t", repr(environ[envitem]) 
         if envitem == 'REQUEST_METHOD':
            print "\t", envitem, ":\t", repr(environ[envitem]) 
         if envitem == 'PATH_INFO':
            print "\t", envitem, ":\t", repr(environ[envitem]) 
         if envitem == 'CONTENT_LENGTH':
            print "\t", envitem, ":\t", repr(environ[envitem]) 
      # end
      print "---------------------------------------------"
#      print websupportfuncs.constructFullURL(environ)      
      return self._application(environ, start_response)
      
