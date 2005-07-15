import os

from requestserver import RequestServer
from processrequesterrorhandler import ErrorPrinter
from httpauthentication import HTTPAuthenticator, SimpleDomainController
from requestresolver import RequestResolver
from pyfiledomaincontroller import PyFileServerDomainController

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
      
      application = RequestServer(self._infoHeader)      
      application = HTTPAuthenticator(application, PyFileServerDomainController(servcfg), True, True, False)      
      application = RequestResolver(application)      
      application = ErrorPrinter(application, self._infoHeader) 
      
      self._application = application
 
   def __call__(self, environ, start_response):
      environ['pyfileserver.config'] = self._srvcfg

      print "---------------------------------------------"
      # for debugging purposes
      for envitem in environ.keys():
         if envitem == envitem.upper():
            print "\t", envitem, "\t:\t", repr(environ[envitem]) 
      # end
      print "---------------------------------------------"
            
      return iter(self._application(environ, start_response))
      
