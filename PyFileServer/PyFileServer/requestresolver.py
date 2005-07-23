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



# CONSTANTS
URL_SEP = '/'
        
def resolveRealmURI(mapcfg, requestpath):
    requestpath = urllib.unquote(requestpath)
    mapcfgkeys = mapcfg.keys()
    mapcfgkeys.sort()
    mapcfgkeys.reverse()
    mapdirprefix = ''
    mapdirprefixfound = False
    for tmp_mapdirprefix in mapcfgkeys:
        if requestpath.upper() == tmp_mapdirprefix.upper() or requestpath.upper().startswith(tmp_mapdirprefix.upper() + URL_SEP):
            mapdirprefixfound = True
            mapdirprefix = tmp_mapdirprefix   
            break
                
    if not mapdirprefixfound:
        return (None, None, None)                  
    
    relativepath = requestpath[len(mapdirprefix):]
    localheadpath = mapcfg[mapdirprefix]

    relativepath = relativepath.replace(URL_SEP, os.sep)

    if relativepath.endswith(os.sep):
        relativepath = relativepath[:-len(os.sep)] # remove suffix os.sep since it causes error (SyntaxError) with os.path functions

    normrelativepath = ''
    if relativepath != '':          # avoid adding of .s
        normrelativepath = os.path.normpath(relativepath)   
           
    mappedpath = localheadpath + os.sep + normrelativepath
   
    if(normrelativepath != ""):
        displaypath = mapdirprefix + normrelativepath.replace(os.sep, URL_SEP)
    else:
        displaypath = mapdirprefix 
  
    if os.path.isdir(mappedpath): 
        displaypath = displaypath + URL_SEP

    return (mapdirprefix, mappedpath, displaypath)    
    
    
"""
Performs initial resolution of request to a particular mapped realm.

Also deals with HTTP non-resource specific requests like TRACE and OPTIONS *, which can return 
automatically without resolving to a specific request
"""

class RequestResolver(object):

    def __init__(self, application):
        self._application = application
      
    def __call__(self, environ, start_response):
        self._srvcfg = environ['pyfileserver.config']

        requestmethod =  environ['REQUEST_METHOD']
        requestpath =  environ['PATH_INFO']

        if requestmethod == 'TRACE':
            return doTRACE(environ, start_response)
      
        if requestpath == '*' and requestmethod == 'OPTIONS':
            return doOPTIONS(environ, start_response)
      
        (mappedrealm, mappedpath, displaypath) = resolveRealmURI(environ['pyfileserver.config']['config_mapping'], requestpath)            
   
        if mappedrealm == None:
            raise ProcessRequestError(processrequesterrorhandler.HTTP_NOT_FOUND)
      
        environ['pyfileserver.mappedrealm'] = mappedrealm
        environ['pyfileserver.mappedpath'] = mappedpath 
        environ['pyfileserver.mappedURI'] = displaypath
      
        return self._application(environ, start_response)


    #TRACE pending, but not essential in this case
    def doTRACE(self, environ, start_response):
        raise ProcessRequestError(processrequesterrorhandler.HTTP_NOT_IMPLEMENTED)
      
    def doOPTIONS(self, environ, start_response):
        start_response('200 OK', [('Content-Type', 'text/html'), ('Content-Length','0'), ('DAV','1'), ('Date',HttpDateHelper.getstrftime())])
        return ['']  
              