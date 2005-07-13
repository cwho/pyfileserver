import os
from RequestServer import RequestServer
from ProcessRequestErrorHandler import ErrorPrinter
import MappingConfiguration 

"""
Main application executable. 

Links request server with the other middleware portions
"""

class PyFileApp(object):
   
   def __init__(self):
      self._srvcfg = MappingConfiguration.getConfiguration()
      self._infoHeader = '<A href=\"mailto:' + self._srvcfg['Info_AdminEmail'] + '\">Administrator</A> at ' + self._srvcfg['Info_Organization']
      self._application = ErrorPrinter(RequestServer(self._srvcfg,self._infoHeader), self._infoHeader)
 
   def __call__(self, environ, start_response):
      print "---------------------------------------------"
      # for debugging purposes
      for envitem in environ.keys():
         if envitem == envitem.upper():
            print "\t", envitem, "\t:\t", repr(environ[envitem]) 
      # end
      print "---------------------------------------------"
      
      
      return iter(self._application(environ, start_response))
      
