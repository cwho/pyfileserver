"""
requestresolver
===============

:Module: pyfileserver.requestresolver
:Author: Ho Chun Wei, fuzzybr80(at)gmail.com
:Project: PyFileServer, http://pyfilesync.berlios.de/
:Copyright: Lesser GNU Public License, see LICENSE file attached with package

PyFileServer file sharing
-------------------------

PyFileServer allows the user to specify in PyFileServer.conf a number of 
realms, and a number of users for each realm. 

Realms
   Each realm corresponds to a filestructure on disk to be stored, 
   for example::
   
      addrealm('pubshare','/home/public/share') 
   
   would allow the users to access using WebDAV the directory/file 
   structure at /home/public/share from the url 
   http://<servername:port>/<approot>/pubshare

   The realm name is set as '/pubshare'

   e.g. /home/public/share/PyFileServer/LICENSE becomes accessible as
   http://<servername:port>/<approot>/pubshare/PyFileServer/LICENSE

Users
   A number of username/password pairs can be set for each realm::
      
      adduser('pubshare', 'username', 'password', 'description/unused')
   
   would add a username/password pair to realm /pubshare.

Note: if developers wish to maintain a separate users database, you can 
write your own domain controller for the HTTPAuthenticator. See 
httpauthentication.py and pyfiledomaincontroller.py for more details.


Request Resolver
----------------

This module is specific to the PyFileServer application

WSGI Middleware for Resolving Realm and Paths for the PyFileServer 
application.

Usage::

   from pyfileserver.requestresolver import RequestResolver
   WSGIApp = RequestResolver(InternalWSGIApp)

The RequestResolver resolves the requested URL to the following values 
placed in the environ dictionary::

   url: http://<servername:port>/<approot>/pubshare/PyFileServer/LICENSE
   environ['pyfileserver.mappedrealm'] = /pubshare
   environ['pyfileserver.mappedpath'] = /home/public/share/PyFileServer/LICENSE 
   environ['pyfileserver.mappedURI'] = /pubshare/PyFileServer/LICENSE

The resolver also resolves any relative paths to its canonical absolute path

The RequestResolver also resolves any value in the Destination request 
header, if present, to::
   
   Destination: http://<servername:port>/<approot>/pubshare/PyFileServer/LICENSE-dest
   environ['pyfileserver.destrealm'] = /pubshare
   environ['pyfileserver.destpath'] = /home/public/share/PyFileServer/LICENSE-dest 
   environ['pyfileserver.destURI'] = /pubshare/PyFileServer/LICENSE

Interface
---------

classes::
   
   RequestResolver: Request resolver for PyFileServer
"""


#Remarks:
#@@: If this were just generalized URL mapping, you'd map it like:
#    Incoming:
#        SCRIPT_NAME=<approot>; PATH_INFO=/pubshare/PyFileServer/LICENSE
#    After transforamtion:
#        SCRIPT_NAME=<approot>/pubshare; PATH_INFO=/PyFileServer/LICENSE
#    Then you dispatch to the application that serves '/home/public/share/'
#
#    This uses SCRIPT_NAME and PATH_INFO exactly how they are intended to be
#    used -- they give context about where you are (SCRIPT_NAME) and what you
#    still have to handle (PATH_INFO)
#
#    An example of an dispatcher that does this is paste.urlmap, and you use it
#    like:
#
#      urlmap = paste.urlmap.URLMap()
#      # urlmap is a WSGI application
#      urlmap['/pubshare'] = PyFileServerForPath('/home/public/share')
#
#    Now, that requires that you have a server that is easily
#    instantiated, but that's kind of a separate concern -- what you
#    really want is to do more general configuration at another level.  E.g.,
#    you might have::
#
#      app = config(urlmap, config_file)
#
#    Which adds the configuration from that file to the request, and
#    PyFileServerForPath then fetches that configuration.  paste.deploy
#    has another way of doing that at instantiation-time; either way
#    though you want to inherit configuration you can still use more general
#    dispatching.
#
#    Incidentally some WebDAV servers do redirection based on the user
#    agent (Zope most notably).  This is because of how WebDAV reuses
#    GET in an obnxious way, so that if you want to use WebDAV on pages
#    that also include dynamic content you have to mount the whole
#    thing at another point in the URL space, so you can GET the
#    content without rendering the dynamic parts.  I don't actually
#    like using user agents -- I'd rather mount the same resources at
#    two different URLs -- but it's just an example of another kind of
#    dispatching that can be done at a higher level.
#
#RR: I think its really an architectural difference - between having a resolver
#    sending requests to different shares to the same application (with different
#    parameters) vs having a URL dispatcher sending the requests to each specific 
#    application for different shares.
#    
#    What's stopping having different
#    applications for different shares at the moment is the reliance on a single
#    locking and dead properties library. Perhaps this can be revisited after that
#    is solved.   


__docformat__ = 'reStructuredText'

# Python Built-in imports
import os
import os.path
import sys
import stat
import urllib
import time
import mimetypes
import cgi
import re

# PyFileServer Imports
import processrequesterrorhandler
from processrequesterrorhandler import HTTPRequestException
import websupportfuncs
import httpdatehelper

        
def resolveRealmURI(mapcfg, requestpath):
    requestpath = urllib.unquote(requestpath)

    # sorting by reverse length
    mapcfgkeys = mapcfg.keys()
    mapcfgkeys.sort(key = len, reverse = True)

    mapdirprefix = ''

    for tmp_mapdirprefix in mapcfgkeys:
        # @@: Case sensitivity should be an option of some sort here; 
        #     os.path.normpath might give the prefered case for a filename.
        if requestpath.upper() == tmp_mapdirprefix.upper() or requestpath.upper().startswith(tmp_mapdirprefix.upper() + "/"):
            mapdirprefix = tmp_mapdirprefix   
            break
    else:
        # @@: perhaps this should raise an exception here
        return (None, None, None)
    
    # no security risk here - the relativepath (part of the URL) is canonized using
    # normpath, and then the share directory name is added. So it is not possible to 
    # use ..s to peruse out of the share directory.
    relativepath = requestpath[len(mapdirprefix):]
    localheadpath = mapcfg[mapdirprefix]

    relativepath = relativepath.replace("/", os.sep)

    if relativepath.endswith(os.sep):
        relativepath = relativepath[:-len(os.sep)] # remove suffix os.sep since it causes error (SyntaxError) with os.path functions

    normrelativepath = ''
    if relativepath != '':          # avoid adding of .s
        normrelativepath = os.path.normpath(relativepath)   
           
    mappedpath = localheadpath + os.sep + normrelativepath
   
    if(normrelativepath != ""):
        displaypath = mapdirprefix + normrelativepath.replace(os.sep, "/")
    else:
        displaypath = mapdirprefix 
  
    if os.path.isdir(mappedpath): 
        displaypath = displaypath + "/"

    return (mapdirprefix, mappedpath, displaypath)    
    

class RequestResolver(object):

    def __init__(self, application):
        self._application = application
      
    def __call__(self, environ, start_response):
        self._srvcfg = environ['pyfileserver.config']

        requestmethod =  environ['REQUEST_METHOD']
        requestpath =  environ['PATH_INFO']

        if requestmethod == 'TRACE':
            return self.doTRACE(environ, start_response)
      
        if requestpath == '*' and requestmethod == 'OPTIONS':
            return self.doOPTIONS(environ, start_response)

        if requestpath == '/' and requestmethod == 'OPTIONS':  #hotfix for WinXP
            return self.doOPTIONS(environ, start_response)

        if 'config_mapping' not in environ['pyfileserver.config']:
            if requestmethod == 'GET': 
                self.printConfigErrorMessage()
            else:
                raise HTTPRequestException(processrequesterrorhandler.HTTP_NOT_FOUND)
    
        (mappedrealm, mappedpath, displaypath) = resolveRealmURI(environ['pyfileserver.config']['config_mapping'], requestpath)            
   
        if mappedrealm is None:
            raise HTTPRequestException(processrequesterrorhandler.HTTP_NOT_FOUND)

        environ['pyfileserver.mappedrealm'] = mappedrealm
        environ['pyfileserver.mappedpath'] = mappedpath 
        environ['pyfileserver.mappedURI'] = displaypath

        if 'HTTP_DESTINATION' in environ:
            desturl = websupportfuncs.getRelativeURL(environ['HTTP_DESTINATION'], environ)
            (destrealm, destpath, destdisplaypath) = resolveRealmURI(environ['pyfileserver.config']['config_mapping'], desturl)            
      
            if destrealm is None:
                 raise HTTPRequestException(processrequesterrorhandler.HTTP_BAD_REQUEST)
   
            environ['pyfileserver.destrealm'] = destrealm
            environ['pyfileserver.destpath'] = destpath 
            environ['pyfileserver.destURI'] = destdisplaypath
      

        if requestmethod == 'OPTIONS':
            return self.doOPTIONSSpec(environ, start_response)
      
        return self._application(environ, start_response)

    #TRACE pending, but not essential
    def doTRACE(self, environ, start_response):
        raise HTTPRequestException(processrequesterrorhandler.HTTP_NOT_IMPLEMENTED)
      
    def doOPTIONS(self, environ, start_response):
        headers = []
        headers.append( ('Content-Type', 'text/html') )
        headers.append( ('Content-Length','0') )
        headers.append( ('DAV','1,2') )
        headers.append( ('Server','DAV/2') )
        headers.append( ('Date',httpdatehelper.getstrftime()) )
        start_response('200 OK', headers)        
        return ['']  

    def doOPTIONSSpec(self, environ, start_response):
        headers = []
        if os.path.isdir(environ['pyfileserver.mappedpath']):
            headers.append( ('Allow','OPTIONS HEAD GET DELETE PROPFIND PROPPATCH COPY MOVE LOCK UNLOCK') )
        elif os.path.isfile(environ['pyfileserver.mappedpath']):
            headers.append( ('Allow','OPTIONS HEAD GET PUT DELETE PROPFIND PROPPATCH COPY MOVE LOCK UNLOCK') )
            headers.append( ('Allow-Ranges','bytes') )
        elif os.path.isdir(os.path.dirname(environ['pyfileserver.mappedpath'])):
            headers.append( ('Allow','OPTIONS PUT MKCOL') )
        else:
            raise HTTPRequestException(processrequesterrorhandler.HTTP_NOT_FOUND)
        headers.append( ('Content-Type', 'text/html') )
        headers.append( ('Content-Length','0') )
        headers.append( ('DAV','1,2') )
        headers.append( ('Server','DAV/2') )
        headers.append( ('Date',httpdatehelper.getstrftime()) )
        start_response('200 OK', headers)        
        return ['']     
    
    def printConfigErrorMessage(self):        
        message = """\
<html><head><title>Welcome to PyFileServer</title></head>
<body>
<h1>Welcome to PyFileServer</h1>
<p>Thank you for using <a href="http://pyfilesync.berlios.de/">PyFileServer</a> .If you are seeing this message, you have either not specified any realm/mappings to be shared or PyFileServer is having difficulties reading your configuration file. Please check that you have specified a valid configuration file.</p>
</body>        
</html>        
        """
        start_response('200 OK', [('Cache-Control','no-cache'), ('Content-Type', 'text/html'), ('Date',httpdatehelper.getstrftime())])
        return [message]          
    
