# @@: I think this module in general could be more generally seen as a case
#     of dispatching different URL prefixes to different applications.
#     Continued below...

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

@@: If this were just generalized URL mapping, you'd map it like:
    Incoming:
        SCRIPT_NAME=<approot>; PATH_INFO=/pubshare/PyFileServer/LICENSE
    After transforamtion:
        SCRIPT_NAME=<approot>/pubshare; PATH_INFO=/PyFileServer/LICENSE
    Then you dispatch to the application that serves '/home/public/share/'

    This uses SCRIPT_NAME and PATH_INFO exactly how they are intended to be
    used -- they give context about where you are (SCRIPT_NAME) and what you
    still have to handle (PATH_INFO)

    An example of an dispatcher that does this is paste.urlmap, and you use it
    like:

      urlmap = paste.urlmap.URLMap()
      # urlmap is a WSGI application
      urlmap['/pubshare'] = PyFileServerForPath('/home/public/share')

    Now, that requires that you have a server that is easily
    instantiated, but that's kind of a separate concern -- what you
    really want is to do more general configuration at another level.  E.g.,
    you might have::

      app = config(urlmap, config_file)

    Which adds the configuration from that file to the request, and
    PyFileServerForPath then fetches that configuration.  paste.deploy
    has another way of doing that at instantiation-time; either way
    though you want to inherit configuration you can still use more general
    dispatching.

    Incidentally some WebDAV servers do redirection based on the user
    agent (Zope most notably).  This is because of how WebDAV reuses
    GET in an obnxious way, so that if you want to use WebDAV on pages
    that also include dynamic content you have to mount the whole
    thing at another point in the URL space, so you can GET the
    content without rendering the dynamic parts.  I don't actually
    like using user agents -- I'd rather mount the same resources at
    two different URLs -- but it's just an example of another kind of
    dispatching that can be done at a higher level.

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

# @@: This is a constant that can never change, since / will always be the URL separator.
#     I think embedding the character in the code is actually better in this case.
# CONSTANTS
URL_SEP = '/'
        
def resolveRealmURI(mapcfg, requestpath):
    requestpath = urllib.unquote(requestpath)
    # @@: I don't think you want to sort these alphabetically; instead they should be
    # sorted by length (longest-first), since the longest paths are the most specific
    mapcfgkeys = mapcfg.keys()
    mapcfgkeys.sort()
    mapcfgkeys.reverse()
    mapdirprefix = ''
    mapdirprefixfound = False
    for tmp_mapdirprefix in mapcfgkeys:
        # @@: Case sensitivity should be an option of some sort; while it is conventional
        # on Windows, it's not conventional elsewhere, and generally even Windows will
        # preserve case so long as you give it the option.  Really if you want to be
        # case-insensitive it's best to redirect to the canonical case of the resource
        # (but maybe only for GET, since other operations can't be safely redirected --
        # but as long as you redirect early it's unlikely someone will access anything
        # with the wrong case).  I'm not sure, but os.path.normpath might give the
        # prefered case for a filename.
        if requestpath.upper() == tmp_mapdirprefix.upper() or requestpath.upper().startswith(tmp_mapdirprefix.upper() + URL_SEP):
            mapdirprefixfound = True
            mapdirprefix = tmp_mapdirprefix   
            break

    # @@: I haven't looked at the calling context yet, but generally it's best to raise
    # an exception in a case like this.
    # But anyway, you can do something like:
    #   for try_prefix in mapcfgkeys:
    #       if try_prefix matches:
    #           ...
    #           break
    #   else:
    #       (this code gets run when the for loop doesn't terminate with "break")
    if not mapdirprefixfound:
        return (None, None, None)

    # There's a possible security risk here, as someone could request "/pubdir/../../foobar".
    # Browsers won't make this sort of request, but someone could construct a request that
    # does this.  A simple assertion later on will protect against this; normalize the path
    # with os.path.normpath, then assert that it starts with the thing you expect it to start
    # with.  You don't really have to give proper HTTP error messages to hacking attempts,
    # so letting the AssertionError go uncatched in fine.  Well... actually you can just raise
    # a Bad Request error.
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

        if requestpath == '/' and requestmethod == 'OPTIONS':
            return self.doOPTIONS(environ, start_response)

        if 'config_mapping' not in environ['pyfileserver.config']:
            if requestmethod == 'GET': 
                self.printConfigErrorMessage()
            else:
                raise HTTPRequestException(processrequesterrorhandler.HTTP_NOT_FOUND)
    
        (mappedrealm, mappedpath, displaypath) = resolveRealmURI(environ['pyfileserver.config']['config_mapping'], requestpath)            
   
        if mappedrealm == None:
            raise HTTPRequestException(processrequesterrorhandler.HTTP_NOT_FOUND)

        environ['pyfileserver.mappedrealm'] = mappedrealm
        environ['pyfileserver.mappedpath'] = mappedpath 
        environ['pyfileserver.mappedURI'] = displaypath

        if 'HTTP_DESTINATION' in environ:
            desturl = websupportfuncs.getRelativeURL(environ['HTTP_DESTINATION'], environ)
            (destrealm, destpath, destdisplaypath) = resolveRealmURI(environ['pyfileserver.config']['config_mapping'], desturl)            
      
            if destrealm == None:
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
        start_response('200 OK', [('Content-Type', 'text/html'), ('Content-Length','0'), ('DAV','1,2'), ('Server','DAV/2'),('Date',httpdatehelper.getstrftime())])
        return ['']  

    def doOPTIONSSpec(self, environ, start_response):
        mappedpath = environ['pyfileserver.mappedpath']
        if os.path.isdir(mappedpath):
            start_response('200 OK', [('Content-Type', 'text/html'), ('Content-Length','0'), ('Allow','OPTIONS HEAD GET DELETE PROPFIND PROPPATCH COPY MOVE LOCK UNLOCK'), ('DAV','1,2'), ('Server','DAV/2'),('Date',httpdatehelper.getstrftime())])      
        elif os.path.isfile(mappedpath):
            start_response('200 OK', [('Content-Type', 'text/html'), ('Content-Length','0'), ('Allow','OPTIONS HEAD GET PUT DELETE PROPFIND PROPPATCH COPY MOVE LOCK UNLOCK'), ('DAV','1,2'), ('Allow-Ranges','bytes'), ('Date',httpdatehelper.getstrftime())])            
        elif os.path.isdir(os.path.dirname(mappedpath)):
            start_response('200 OK', [('Content-Type', 'text/html'), ('Content-Length','0'), ('Allow','OPTIONS PUT MKCOL'), ('DAV','1,2'), ('Date',httpdatehelper.getstrftime())])      
        else:
            raise HTTPRequestException(processrequesterrorhandler.HTTP_NOT_FOUND)
        # @@: I'd say that return [''] is generally better, as you don't set up an unnecessary
        # generator context
        yield ''
        return      
    
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
        # @@: ditto on the return; you should only use yield when you really are doing
        # extra work on each iteration
        yield message          
        return
    
