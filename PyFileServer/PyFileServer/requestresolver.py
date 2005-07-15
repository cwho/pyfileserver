import os
import os.path
import sys
import stat
import urllib
import time
import mimetypes
import cgi
import re

from processrequesterrorhandler import ProcessRequestError
import processrequesterrorhandler


"""
Performs initial resolution of request to a particular mapped realm.

Also deals with HTTP non-resource specific requests like TRACE and OPTIONS *, which can return 
automatically without resolving to a specific request
"""

# CONSTANTS
URL_SEP = '/'


class RequestResolver(object):

    def __init__(self, application):
        self._application = application
      
    def __call__(self, environ, start_response):
        self._srvcfg = environ['pyfileserver.config']

        requestmethod =  environ['REQUEST_METHOD']
        requestpath =  urllib.unquote(environ['PATH_INFO'])

        #if requestmethod == 'GET' and requestpath == '/favicon.ico':
        #    raise ProcessRequestError(processrequesterrorhandler.HTTP_NOT_FOUND)            

        if requestmethod == 'TRACE':
            return doTRACE(environ, start_response)
      
        if requestpath == '*' and requestmethod == 'OPTIONS':
            return doOPTIONSGeneric(environ, start_response)
      
        mapcfg = self._srvcfg['config_mapping']
        mapcfgkeys = mapcfg.keys()
        mapcfgkeys.sort()
        mapcfgkeys.reverse()
        mapdirprefix = ''
        mapdirprefixfound = False
        for tmp_mapdirprefix in mapcfgkeys:
            if self._srvcfg['MapKeysCaseSensitive'] == 1: 
                if requestpath == tmp_mapdirprefix or requestpath.startswith(tmp_mapdirprefix + URL_SEP):
                    mapdirprefixfound = True
                    mapdirprefix = tmp_mapdirprefix   
                    break         
            else:
                if requestpath.upper() == tmp_mapdirprefix.upper() or requestpath.upper().startswith(tmp_mapdirprefix.upper() + URL_SEP):
                    mapdirprefixfound = True
                    mapdirprefix = tmp_mapdirprefix   
                    break         
   
        if not mapdirprefixfound:
            raise ProcessRequestError(processrequesterrorhandler.HTTP_NOT_FOUND)
            
      
        environ['pyfileserver.mappedrealm'] = mapdirprefix
        environ['pyfileserver.mappedrealmrelativeurl'] = requestpath[len(mapdirprefix):] 
        environ['pyfileserver.mappedrealmlocaldir'] = mapcfg[mapdirprefix]
      
        return self._application(environ, start_response)


    #TRACE pending, but not essential in this case
    def doTRACE(self, environ, start_response):
        raise ProcessRequestError(processrequesterrorhandler.HTTP_NOT_IMPLEMENTED)
      
    def doOPTIONSGeneric(self, environ, start_response):
        start_response('200 OK', [('Content-Type', 'text/html'), ('Content-Length','0'), ('Date',HttpDateHelper.getstrftime())])
        return ['']  