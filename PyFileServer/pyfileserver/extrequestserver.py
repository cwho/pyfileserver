"""
extrequestserver
================

:Module: pyfileserver.extrequestserver
:Author: Ho Chun Wei, fuzzybr80(at)gmail.com
:Project: PyFileServer, http://pyfilesync.berlios.de/
:Copyright: Lesser GNU Public License, see LICENSE file attached with package

This is the main implementation module for the various webDAV methods. Each 
method is implemented as a do<METHOD> generator function that is a wsgi 
subapplication::

   class RequestServer(object)

      constructor :
         __init__(self, propertymanager, 
                        lockmanager, 
                        etagproviderfunc)
   
      main application:      
         __call__(self, environ, start_response)

      application methods:
         doPUT(self, environ, start_response)
         doOPTIONS(self, environ, start_response)
         doGETHEADDirectory(self, environ, start_response)
         doGETHEADFile(self, environ, start_response)
         doMKCOL(self, environ, start_response)
         doDELETE(self, environ, start_response)
         doPROPPATCH(self, environ, start_response)
         doPROPFIND(self, environ, start_response)
         doCOPY(self, environ, start_response)
         doMOVE(self, environ, start_response)
         doLOCK(self, environ, start_response)
         doUNLOCK(self, environ, start_response)

      misc methods:
         evaluateSingleIfConditionalDoException(self, mappedpath, displaypath, 
                                   environ, start_response, checkLock = False)
         evaluateSingleHTTPConditionalsDoException(self, mappedpath, 
                                          displaypath, environ, start_response)
   
This module is specific to the PyFileServer application.


Supporting Objects
------------------

The RequestServer takes three supporting objects:   
   
propertymanager
   An object that provides storage for dead properties assigned for webDAV resources.
   
   See propertylibrary.PropertyManager in propertylibrary.py for a sample implementation
   using shelve.

lockmanager
   An object that provides storage for locks made on webDAV resources.
   
   See propertylibrary.LockManager in propertylibrary.py for a sample implementation
   using shelve.

etagproviderfunc
   A function object to provide entitytags for a given filename.
   
   See etagprovider.getETag in etagprovider.py for a sample implementation.

"""

__docformat__ = 'reStructuredText'


import os
import os.path
import sys
import stat
import urllib
import time
import mimetypes
import cgi
import re
import shutil
import StringIO

from processrequesterrorhandler import HTTPRequestException
import processrequesterrorhandler

import websupportfuncs
import httpdatehelper
import etagprovider
import propertylibrary
import requestresolver

from xml.dom.ext.reader import Sax2
import xml.dom.ext
from xml.dom import implementation, Node

# CONSTANTS
URL_SEP = '/'
BUFFER_SIZE = 8192
BUF_SIZE = 8192



class RequestServer(object):
   def __init__(self, propertymanager, lockmanager, etagproviderfunc):
      self._propertymanager = propertymanager
      self._lockmanager = lockmanager
      self._etagprovider = etagproviderfunc
      
   def __call__(self, environ, start_response):

      assert 'pyfileserver.mappedrealm' in environ
      assert 'pyfileserver.mappedpath' in environ
      assert 'pyfileserver.mappedURI' in environ
      assert 'httpauthentication.username' in environ 
      
      environ['pyfileserver.username'] = environ['httpauthentication.username'] 
      requestmethod =  environ['REQUEST_METHOD']   
      mapdirprefix = environ['pyfileserver.mappedrealm']
      mappedpath = environ['pyfileserver.mappedpath']
      displaypath =  environ['pyfileserver.mappedURI']

      if (requestmethod == 'GET' or requestmethod == 'HEAD'):
         if os.path.isdir(mappedpath): 
            return self.doGETHEADDirectory(environ, start_response)
         elif os.path.isfile(mappedpath):
            return self.doGETHEADFile(environ, start_response)
         else:
            raise HTTPRequestException(processrequesterrorhandler.HTTP_NOT_FOUND)               
      elif requestmethod == 'PUT':
         return self.doPUT(environ, start_response)
      elif requestmethod == 'DELETE':
         return self.doDELETE(environ, start_response)
      elif requestmethod == 'OPTIONS':
         return self.doOPTIONS(environ, start_response)
      elif requestmethod == 'MKCOL':
         return self.doMKCOL(environ, start_response)
      elif requestmethod == 'PROPPATCH':
         return self.doPROPPATCH(environ, start_response)
      elif requestmethod == 'PROPFIND':
         return self.doPROPFIND(environ, start_response)
      elif requestmethod == 'COPY':
         return self.doCOPY(environ, start_response)
      elif requestmethod == 'MOVE':
         return self.doMOVE(environ, start_response)
      elif requestmethod == 'LOCK':
         return self.doLOCK(environ, start_response)
      elif requestmethod == 'UNLOCK':
         return self.doUNLOCK(environ, start_response)
      else:
         raise HTTPRequestException(processrequesterrorhandler.HTTP_METHOD_NOT_ALLOWED)


   def doPUT(self, environ, start_response):
      mappedpath = environ['pyfileserver.mappedpath']
      displaypath =  environ['pyfileserver.mappedURI']
      
      if os.path.isdir(mappedpath):
         raise HTTPRequestException(processrequesterrorhandler.HTTP_BAD_REQUEST)

      if not os.path.isdir(os.path.dirname(mappedpath)):
         raise HTTPRequestException(processrequesterrorhandler.HTTP_BAD_REQUEST)

      isnewfile = True
      if os.path.isfile(mappedpath):
         isnewfile = False
         statresults = os.stat(mappedpath)
         mode = statresults[stat.ST_MODE]      
         filesize = statresults[stat.ST_SIZE]
         lastmodified = statresults[stat.ST_MTIME]
         entitytag = self._etagprovider(mappedpath)
      else:
         lastmodified = -1
         entitytag = self._etagprovider(mappedpath)

      if isnewfile:
         urlparentpath = websupportfuncs.getLevelUpURL(displaypath)      
         if self._lockmanager.isURLLocked(urlparentpath):
            self.evaluateSingleIfConditionalDoException( os.path.dirname(mappedpath), urlparentpath, environ, start_response, True)

      if os.path.exists(mappedpath) or self._lockmanager.isURLLocked(displaypath) != None:
         self.evaluateSingleIfConditionalDoException( mappedpath, displaypath, environ, start_response, True)
      self.evaluateSingleHTTPConditionalsDoException( mappedpath, displaypath, environ, start_response)

#      websupportfuncs.evaluateHTTPConditionals(lastmodified, entitytag, environ, isnewfile)   

      ## Test for unsupported stuff

      if 'HTTP_CONTENT_ENCODING' in environ:
         raise HTTPRequestException(processrequesterrorhandler.HTTP_NOT_IMPLEMENTED)
         
      if 'HTTP_CONTENT_RANGE' in environ:
         raise HTTPRequestException(processrequesterrorhandler.HTTP_NOT_IMPLEMENTED)
      
      ## Start Content Processing
      
      contentlength = -1
      if 'HTTP_CONTENT_LENGTH' in environ:
         if environ['HTTP_CONTENT_LENGTH'].isdigit():
            contentlength = long(environ['HTTP_CONTENT_LENGTH'])      
      
      isbinaryfile = True
      if 'HTTP_CONTENT_TYPE' in environ:
         if environ['HTTP_CONTENT_TYPE'].lower().startswith('text'):
            isbinaryfile = False
             
      inputstream = environ['wsgi.input']

      contentlengthremaining = contentlength

      try:      
         if isbinaryfile:
            fileobj = file(mappedpath, 'wb', BUFFER_SIZE)
         else:
            fileobj = file(mappedpath, 'w', BUFFER_SIZE)      
   
         #read until EOF or contentlengthremaining = 0
         readbuffer = 'start'
         while len(readbuffer) != 0 and contentlengthremaining != 0:
            if contentlengthremaining == -1 or contentlengthremaining > BUFFER_SIZE:
               next_buffer_read_size = BUFFER_SIZE
            else:
               next_buffer_read_size = contentlengthremaining
               
            readbuffer = inputstream.read(next_buffer_read_size)
            if len(readbuffer) != 0:
               contentlengthremaining = contentlengthremaining - len(readbuffer)
               fileobj.write(readbuffer)         
               fileobj.flush()         
                  
         fileobj.close()
         self._lockmanager.checkLocksToAdd(displaypath)

      except:
         raise HTTPRequestException(processrequesterrorhandler.HTTP_INTERNAL_ERROR) 
      
      if isnewfile:
         start_response('201 Created', [('Content-Type', 'text/html'), ('Content-Length','0'), ('Date',httpdatehelper.getstrftime())])
      else:
         start_response('200 OK', [('Content-Type', 'text/html'), ('Content-Length','0'), ('Date',httpdatehelper.getstrftime())])
      
      yield ''
      return
      
        
   def doOPTIONS(self, environ, start_response):
      mappedpath = environ['pyfileserver.mappedpath']
      if os.path.isdir(mappedpath):
         start_response('200 OK', [('Content-Type', 'text/html'), ('Content-Length','0'), ('Allow','OPTIONS HEAD GET DELETE PROPFIND PROPPATCH COPY MOVE LOCK UNLOCK'), ('DAV','1,2'), ('Date',httpdatehelper.getstrftime())])      
      elif os.path.isfile(mappedpath):
         start_response('200 OK', [('Content-Type', 'text/html'), ('Content-Length','0'), ('Allow','OPTIONS HEAD GET PUT DELETE PROPFIND PROPPATCH COPY MOVE LOCK UNLOCK'), ('DAV','1,2'), ('Allow-Ranges','bytes'), ('Date',httpdatehelper.getstrftime())])            
      elif os.path.isdir(os.path.dirname(mappedpath)):
         start_response('200 OK', [('Content-Type', 'text/html'), ('Content-Length','0'), ('Allow','OPTIONS PUT MKCOL'), ('DAV','1,2'), ('Date',httpdatehelper.getstrftime())])      
      else:
         raise HTTPRequestException(processrequesterrorhandler.HTTP_NOT_FOUND)         
      yield ''
      return      




   def doGETHEADDirectory(self, environ, start_response):
      
      if environ['REQUEST_METHOD'] == 'HEAD':
         start_response('200 OK', [('Content-Type', 'text/html'), ('Date',httpdatehelper.getstrftime())])
         yield ''
         return 

      environ['HTTP_DEPTH'] = '0' #nothing else allowed
      mappedpath = environ['pyfileserver.mappedpath']
      mapdirprefix = environ['pyfileserver.mappedrealm']
      displaypath =  environ['pyfileserver.mappedURI']

      self.evaluateSingleIfConditionalDoException( mappedpath, displaypath, environ, start_response)
      self.evaluateSingleHTTPConditionalsDoException( mappedpath, displaypath, environ, start_response)
      
      trailer = ''
      if 'pyfileserver.trailer' in environ:
         trailer = environ['pyfileserver.trailer']

      proc_response = ''
      proc_response = proc_response + ('<html><head><title>PyFileServer - Index of ' + displaypath + '</title>')
      
      proc_response = proc_response + ('<style type="text/css">\nimg { border: 0; padding: 0 2px; vertical-align: text-bottom; }\ntd  { font-family: monospace; padding: 2px 3px; text-align: right; vertical-align: bottom; white-space: pre; }\ntd:first-child { text-align: left; padding: 2px 10px 2px 3px; }\ntable { border: 0; }\na.symlink { font-style: italic; }</style>')
      proc_response = proc_response + ('</head>\n')
      proc_response = proc_response + ('<body>')
      proc_response = proc_response + ('<H1>' + displaypath + '</H1>')
      proc_response = proc_response + ('<hr/><table>')
      
      if displaypath == mapdirprefix or displaypath == mapdirprefix + URL_SEP:
         proc_response = proc_response + ('<tr><td colspan="4">Top level share directory</td></tr>')
      else:
         proc_response = proc_response + ('<tr><td colspan="4"><a href="' + websupportfuncs.getLevelUpURL(displaypath) + '">Up to higher level directory</a></td></tr>')
    
      for f in os.listdir(mappedpath):
          proc_response = proc_response + '<tr>'
          proc_response = proc_response + '<td><A HREF="' + websupportfuncs.cleanUpURL(displaypath + URL_SEP + f) + '">'+ f + '</A></td>'
   
          pathname = os.path.join(mappedpath, f)
          statresults = os.stat(pathname)
          mode = statresults[stat.ST_MODE]
   
          if stat.S_ISDIR(mode):
             proc_response = proc_response + '<td>Directory</td>' + '<td></td>'
          elif stat.S_ISREG(mode):
             proc_response = proc_response + '<td>File</td>' + '<td>' + str(statresults[stat.ST_SIZE]) + ' B </td>'
          else:
             proc_response = proc_response + '<td>Unknown</td>' + '<td>' + str(statresults[stat.ST_SIZE]) + ' B </td>'
   
          proc_response = proc_response + '<td>' + httpdatehelper.getstrftime(statresults[stat.ST_MTIME]) + '</td>'
          proc_response = proc_response + '</tr>\n'
   
      proc_response = proc_response + ('</table><hr>')
      proc_response = proc_response + trailer + '<BR>'
      proc_response = proc_response + httpdatehelper.getstrftime()
      proc_response = proc_response + ('</body></html>\n')
      start_response('200 OK', [('Content-Type', 'text/html'), ('Date',httpdatehelper.getstrftime())])
      yield proc_response
      return





   # supports If and HTTP If Conditionals
   def doGETHEADFile(self, environ, start_response):

      environ['HTTP_DEPTH'] = '0' #nothing else allowed
      mappedpath = environ['pyfileserver.mappedpath']
      displaypath =  environ['pyfileserver.mappedURI']

      self.evaluateSingleIfConditionalDoException( mappedpath, displaypath, environ, start_response)
      self.evaluateSingleHTTPConditionalsDoException( mappedpath, displaypath, environ, start_response)

            
      statresults = os.stat(mappedpath)
      mode = statresults[stat.ST_MODE]   
      filesize = statresults[stat.ST_SIZE]
      lastmodified = statresults[stat.ST_MTIME]
      entitytag = self._etagprovider(mappedpath)


      ## Ranges      
      doignoreranges = False
      if 'HTTP_RANGE' in environ and 'HTTP_IF_RANGE' in environ:
         ifrange = environ['HTTP_IF_RANGE']
         #try as http-date first
         secstime = httpdatehelper.getsecstime(ifrange)
         if secstime:
            if lastmodified != secstime:
               doignoreranges = True
         else:
            #use as entity tag
            ifrange = ifrange.strip("\" ")
            if ifrange != entitytag:
               doignoreranges = True

      ispartialranges = False
      if 'HTTP_RANGE' in environ and not doignoreranges:
         ispartialranges = True
         listRanges, totallength = websupportfuncs.obtainContentRanges(environ['HTTP_RANGE'], filesize)
         if len(listRanges) == 0:
            #No valid ranges present
            raise HTTPRequestException(processrequesterrorhandler.HTTP_RANGE_NOT_SATISFIABLE)

         #More than one range present -> take only the first range, since multiple range returns require multipart, which is not supported         
         #obtainContentRanges supports more than one range in case the above behaviour changes in future
         (rangestart, rangeend, rangelength) = listRanges[0]
      else:
         (rangestart, rangeend, rangelength) = (0L, filesize - 1, filesize)
         totallength = filesize

      ## Content Processing 

      (mimetype, mimeencoding) = mimetypes.guess_type(mappedpath); 
      if mimetype == '' or mimetype == None:
         mimetype = 'application/octet-stream' 
      
      responseHeaders = []
      responseHeaders.append(('Content-Length', rangelength))
      responseHeaders.append(('Last-Modified', httpdatehelper.getstrftime(lastmodified)))
      responseHeaders.append(('Content-Type', mimetype))
      responseHeaders.append(('Date', httpdatehelper.getstrftime()))
      responseHeaders.append(('ETag', '\"' + entitytag + '\"'))
      if ispartialranges:
         responseHeaders.append(('Content-Ranges', 'bytes ' + str(rangestart) + '-' + str(rangeend) + '/' + rangelength))
         start_response('206 Partial Content', responseHeaders)   
      else:
         start_response('200 OK', responseHeaders)

      if environ['REQUEST_METHOD'] == 'HEAD':
         yield ''
         return

      if mimetype.startswith("text"):
         fileobj = file(mappedpath, 'r', BUFFER_SIZE)
      else:
         fileobj = file(mappedpath, 'rb', BUFFER_SIZE)

      fileobj.seek(rangestart)
      
      #read until EOF or contentlengthremaining = 0
      contentlengthremaining = rangelength
      readbuffer = 'start'
      while len(readbuffer) != 0 and contentlengthremaining != 0:
         if contentlengthremaining == -1 or contentlengthremaining > BUFFER_SIZE:
            next_buffer_read_size = BUFFER_SIZE
         else:
            next_buffer_read_size = contentlengthremaining
            
         readbuffer = fileobj.read(next_buffer_read_size)
         if len(readbuffer) != 0:
            contentlengthremaining = contentlengthremaining - len(readbuffer)
            yield readbuffer
   
      fileobj.close()
      return

   
   def doMKCOL(self, environ, start_response):               
      if 'CONTENT_LENGTH' in environ:
         if environ['CONTENT_LENGTH'].isdigit() and environ['CONTENT_LENGTH'] != '0': 
            #Do not understand ANY request body entities
            raise HTTPRequestException(processrequesterrorhandler.HTTP_MEDIATYPE_NOT_SUPPORTED)

      environ['HTTP_DEPTH'] = '0' #nothing else allowed
      mappedpath = environ['pyfileserver.mappedpath']
      displaypath =  environ['pyfileserver.mappedURI']
      
      if os.path.exists(mappedpath) or self._lockmanager.isURLLocked(displaypath) != None:
         self.evaluateSingleIfConditionalDoException( mappedpath, displaypath, environ, start_response, True)
      self.evaluateSingleHTTPConditionalsDoException( mappedpath, displaypath, environ, start_response)
      
      if os.path.exists(mappedpath):
         raise HTTPRequestException(processrequesterrorhandler.HTTP_METHOD_NOT_ALLOWED)         

      parentdir = os.path.dirname(mappedpath)
            
      urlparentpath = websupportfuncs.getLevelUpURL(displaypath)      
      if self._lockmanager.isURLLocked(urlparentpath):
         self.evaluateSingleIfConditionalDoException( parentdir, urlparentpath, environ, start_response, True)


      
      if not os.path.isdir(parentdir):
         raise HTTPRequestException(processrequesterrorhandler.HTTP_CONFLICT)          
      try:   
         os.mkdir(mappedpath)
         self._lockmanager.checkLocksToAdd(displaypath)
      except Exception:
         pass
      if os.path.exists(mappedpath):
         start_response("201 Created", [('Content-Length',0)])
      else:
         start_response("200 OK", [('Content-Length',0)])
      yield ''
      return

   def doDELETE(self, environ, start_response):
      mappedpath = environ['pyfileserver.mappedpath']
      displaypath =  environ['pyfileserver.mappedURI']

      if not os.path.exists(mappedpath):
         raise HTTPRequestException(processrequesterrorhandler.HTTP_NOT_FOUND)         

      if os.path.isdir(mappedpath): #delete over collection
         environ['HTTP_DEPTH'] = 'infinity'
      else:
         environ['HTTP_DEPTH'] = '0'

      actionList = websupportfuncs.getDepthActionList(mappedpath, displaypath, environ['HTTP_DEPTH'], False)

      dictError = dict([]) #errors in deletion
      dictHidden = dict([]) #hidden errors, ancestors of failed deletes
      for (filepath, filedisplaypath) in actionList:         
         if filepath not in dictHidden:
            try:
               
               urlparentpath = websupportfuncs.getLevelUpURL(filedisplaypath)
               if self._lockmanager.isURLLocked(urlparentpath):
                  self.evaluateSingleIfConditionalDoException( os.path.dirname(filepath), urlparentpath, environ, start_response, True)
                  
               self.evaluateSingleIfConditionalDoException( filepath, filedisplaypath, environ, start_response, True)
               self.evaluateSingleHTTPConditionalsDoException( filepath, filedisplaypath, environ, start_response)

               if os.path.isdir(filepath):
                  os.rmdir(filepath)
               else:
                  os.unlink(filepath)
               self._propertymanager.removeProperties(filedisplaypath)
               self._lockmanager.removeAllLocksFromURL(filedisplaypath)
            except HTTPRequestException, e:
               dictError[filedisplaypath] = processrequesterrorhandler.interpretErrorException(e)
               dictHidden[os.path.dirname(filepath)] = ''
            except Exception:
               pass
            if os.path.exists(filepath) and filedisplaypath not in dictError:
               dictError[filedisplaypath] = '500 Internal Server Error'
               dictHidden[os.path.dirname(filepath)] = ''
         else:
            dictHidden[os.path.dirname(filepath)] = ''

      if len(dictError) == 1 and displaypath in dictError:
         start_response(dictError[displaypath], [('Content-Length','0')])
         yield ''      
      elif len(dictError) > 0:
         start_response('207 Multi Status', [('Content-Length','0')])
         yield "<?xml version='1.0' ?>\n<D:multistatus xmlns:D='DAV:'>"
         for filedisplaypath in dictError.keys():
            yield "<D:response>\n<D:href>" + websupportfuncs.constructFullURL(filedisplaypath, environ) + "</D:href>"            
            yield "<D:status>HTTP/1.1 " + dictError[filedisplaypath] + "</D:status>\n</D:response>"            
         yield "</D:multistatus>"
      else:
         start_response('204 No Content', [('Content-Length','0')])
         yield ''
      return


   def doPROPPATCH(self, environ, start_response):
      environ['HTTP_DEPTH'] = '0' #nothing else allowed
      mappedpath = environ['pyfileserver.mappedpath']
      displaypath =  environ['pyfileserver.mappedURI']
      
      self.evaluateSingleIfConditionalDoException( mappedpath, displaypath, environ, start_response, True)
      self.evaluateSingleHTTPConditionalsDoException( mappedpath, displaypath, environ, start_response)

      contentlengthtoread = 0
      if 'CONTENT_LENGTH' in environ:
         if environ['CONTENT_LENGTH'].isdigit():
            contentlengthtoread = long(environ['CONTENT_LENGTH'])

      requestbody = ''
      if 'wsgi.input' in environ and contentlengthtoread > 0:
         inputstream = environ['wsgi.input']  
         readsize = BUF_SIZE
         if contentlengthtoread < BUF_SIZE:
            readsize = contentlengthtoread    
         readbuffer = inputstream.read(readsize)
         contentlengthtoread = contentlengthtoread - readsize
         requestbody = requestbody + readbuffer
         while len(readbuffer) != 0 and contentlengthtoread > 0:
            readsize = BUF_SIZE
            if contentlengthtoread < BUF_SIZE:
               readsize = contentlengthtoread    
            readbuffer = inputstream.read(readsize)
            contentlengthtoread = contentlengthtoread - readsize
            requestbody = requestbody + readbuffer

      try:
         doc = Sax2.Reader().fromString(requestbody)
      except Exception:
         raise HTTPRequestException(processrequesterrorhandler.HTTP_BAD_REQUEST)   
      pproot = doc.documentElement
      if pproot.namespaceURI != 'DAV:' or pproot.localName != 'propertyupdate':
         raise HTTPRequestException(processrequesterrorhandler.HTTP_BAD_REQUEST)   

      propupdatelist = []
      for ppnode in pproot.childNodes:
         if ppnode.namespaceURI == 'DAV:' and (ppnode.localName == 'remove' or ppnode.localName == 'set'):
            for propnode in ppnode.childNodes:
               if propnode.namespaceURI == 'DAV:' and propnode.localName == 'prop':
                  for propertynode in propnode.childNodes: 
                     if propertynode.nodeType == xml.dom.Node.ELEMENT_NODE:                     
                        propvalue = None
                        if ppnode.localName == 'set':
                           if len(propertynode.childNodes) == 1 and propertynode.firstChild.nodeType == xml.dom.Node.TEXT_NODE:
                              propvalue = propertynode.firstChild.nodeValue
                           else:
                              propvaluestream = StringIO.StringIO()
                              for childnode in propertynode.childNodes:
                                 xml.dom.ext.PrettyPrint(childnode, stream=propvaluestream)
                              propvalue = propvaluestream.getvalue()
                              propvaluestream.close()
                              
                        verifyns = propertynode.namespaceURI
                        if verifyns == None:
                           verifyns = ''
                        propupdatelist.append( ( verifyns , propertynode.localName , ppnode.localName , propvalue) )

      successflag = True
      writeresultlist = []
      for (propns, propname , propmethod , propvalue) in propupdatelist:
         writeresult = propertylibrary.writeProperty(self._propertymanager, mappedpath, displaypath, propns, propname , propmethod , propvalue, False)
         writeresultlist.append( (propns, propname, writeresult) )
         successflag = successflag and writeresult == "200 OK"

      start_response('207 Multistatus', [('Content-Type','text/xml'), ('Date',httpdatehelper.getstrftime())])
   
      if successflag:
         yield "<?xml version='1.0' ?>\n<D:multistatus xmlns:D='DAV:'>\n<D:response>"
         yield "<D:href>" + websupportfuncs.constructFullURL(displaypath, environ) + "</D:href>"    
         laststatus = ''
         for (propns, propname , propmethod , propvalue) in propupdatelist:
            propstatus = propertylibrary.writeProperty(self._propertymanager, mappedpath, displaypath, propns, propname , propmethod , propvalue, True)
            if laststatus == '':
               yield "<D:propstat>\n<D:prop>"                                  
            if propstatus != laststatus and laststatus != '':
               yield "</D:prop>\n<D:status>HTTP/1.1 " + laststatus + "</D:status>\n</D:propstat>\n<D:propstat>\n<D:prop>" 
            if propns == 'DAV:':
               yield "<D:" + propname + "/>"
            else:
               if propns != None and propns != '':
                  yield "<A:" + propname + " xmlns:A='" + propns + "'/>"
               else:
                  yield "<" + propname + " xmlns='" + propns + "'/>"
            laststatus = propstatus
         if laststatus != '':
            yield "</D:prop>\n<D:status>HTTP/1.1 " + laststatus + "</D:status>\n</D:propstat>"         
         yield "</D:response>\n</D:multistatus>"
      else:
         yield "<?xml version='1.0' ?>\n<D:multistatus xmlns:D='DAV:'>\n<D:response>"
         yield "<D:href>" + websupportfuncs.constructFullURL(displaypath, environ) + "</D:href>"    
         laststatus = ''
         for (propns, propname, propstatus) in writeresultlist:
            if propstatus == '200 OK':
               propstatus = '424 Failed Dependency'
            if laststatus == '':
               yield "<D:propstat>\n<D:prop>"                                  
            if propstatus != laststatus and laststatus != '':
               yield "</D:prop>\n<D:status>HTTP/1.1 " + laststatus + "</D:status>\n</D:propstat>\n<D:propstat>\n<D:prop>" 
            if propns == 'DAV:':
               yield "<D:" + propname + "/>"
            else:
               if propns != None and propns != '':
                  yield "<A:" + propname + " xmlns:A='" + propns + "'/>"
               else:
                  yield "<" + propname + " xmlns='" + propns + "'/>"
            laststatus = propstatus
         if laststatus != '':
            yield "</D:prop>\n<D:status>HTTP/1.1 " + laststatus + "</D:status>\n</D:propstat>"         
         yield "</D:response>\n</D:multistatus>"
      return
   
   # does not yet support If and If HTTP Conditions   
   def doPROPFIND(self, environ, start_response):
      if 'HTTP_DEPTH' not in environ:
         environ['HTTP_DEPTH'] = '0'
      mappedpath = environ['pyfileserver.mappedpath']
      displaypath =  environ['pyfileserver.mappedURI']
                  
      contentlengthtoread = 0
      if 'CONTENT_LENGTH' in environ:
         if environ['CONTENT_LENGTH'].isdigit():
            contentlengthtoread = long(environ['CONTENT_LENGTH'])

      requestbody = ''
      if 'wsgi.input' in environ and contentlengthtoread > 0:
         inputstream = environ['wsgi.input']  
         readsize = BUF_SIZE
         if contentlengthtoread < BUF_SIZE:
            readsize = contentlengthtoread    
         readbuffer = inputstream.read(readsize)
         contentlengthtoread = contentlengthtoread - readsize
         requestbody = requestbody + readbuffer
         while len(readbuffer) != 0 and contentlengthtoread > 0:
            readsize = BUF_SIZE
            if contentlengthtoread < BUF_SIZE:
               readsize = contentlengthtoread    
            readbuffer = inputstream.read(readsize)
            contentlengthtoread = contentlengthtoread - readsize
            requestbody = requestbody + readbuffer
         
      if requestbody == '':
         requestbody = "<D:propfind xmlns:D='DAV:'><D:allprop/></D:propfind>"      

      try:
         doc = Sax2.Reader().fromString(requestbody)
      except Exception:
         raise HTTPRequestException(processrequesterrorhandler.HTTP_BAD_REQUEST)   
      pfroot = doc.documentElement
      if pfroot.namespaceURI != 'DAV:' or pfroot.localName != 'propfind':
         raise HTTPRequestException(processrequesterrorhandler.HTTP_BAD_REQUEST)   

      if not os.path.exists(mappedpath):
         raise HTTPRequestException(processrequesterrorhandler.HTTP_NOT_FOUND)

      reslist = websupportfuncs.getDepthActionList(mappedpath, displaypath, environ['HTTP_DEPTH'], True)
            
      propList = []
      propFindMode = 3
      for pfnode in pfroot.childNodes:
         if pfnode.namespaceURI == 'DAV:' and pfnode.localName == 'allprop':
            propFindMode = 1  
            break
         if pfnode.namespaceURI == 'DAV:' and pfnode.localName == 'propname':
            propFindMode = 2       
            break
         if pfnode.namespaceURI == 'DAV:' and pfnode.localName == 'prop':
            pfpList = pfnode.childNodes
            for pfpnode in pfpList:
               if pfpnode.nodeType == xml.dom.Node.ELEMENT_NODE:
                  verifyns = pfpnode.namespaceURI
                  if verifyns == None:
                     verifyns = ''
                  propList.append( (verifyns, pfpnode.localName) )       

      start_response('207 Multistatus', [('Content-Type','text/xml'), ('Date',httpdatehelper.getstrftime())])

      yield "<?xml version='1.0' ?>"
      yield "<D:multistatus xmlns:D='DAV:'>"
      for (respath , resdisplayname) in reslist:
         yield "<D:response>"
         yield "<D:href>" + websupportfuncs.constructFullURL(resdisplayname, environ) + "</D:href>"    

         if propFindMode == 1 or propFindMode == 2:
            propList = propertylibrary.getApplicablePropertyNames(self._propertymanager, respath, resdisplayname)
            
         if propFindMode == 2:
            yield "<D:propstat>\n<D:prop>"
            for (propns, propname) in propList:
               if propns == 'DAV:':
                  yield "<D:" + propname + "/>"
               else:
                  if propns != None and propns != '':
                     yield "<A:" + propname + " xmlns:A='" + propns + "'/>"
                  else:
                     yield "<" + propname + " xmlns='" + propns + "'/>"
            yield "</D:prop>\n<D:status>HTTP/1.1 200 OK</D:status>\n</D:propstat>"
         else:
            laststatus = ''
            for (propns, propname) in propList:
               try:
#                  self.evaluateSingleIfConditionalDoException( filepath, filedisplaypath, environ, start_response)
#                  self.evaluateSingleHTTPConditionalsDoException( filepath, filedisplaypath, environ, start_response)
                  (propvalue, propstatus) = propertylibrary.getProperty(self._propertymanager, self._lockmanager, respath, resdisplayname, propns, propname, self._etagprovider)   
               except HTTPRequestException, e:
                  propvalue = ''
                  propstatus = processrequesterrorhandler.interpretErrorException(e)
               if laststatus == '':
                  yield "<D:propstat>\n<D:prop>"                                  
               if propstatus != laststatus and laststatus != '':
                  yield "</D:prop>\n<D:status>HTTP/1.1 " + laststatus + "</D:status>\n</D:propstat>\n<D:propstat>\n<D:prop>" 
               if propvalue == None:
                  propvalue = '';               
               if propns == 'DAV:':
                  yield "<D:" + propname + ">"
                  yield propvalue.encode('utf-8') 
                  yield "</D:"+propname+">"
               else:
                  if propns != None and propns != '':
                     yield "<A:" + propname + " xmlns:A='" + propns + "' >"
                     yield propvalue.encode('utf-8') 
                     yield "</A:"+propname+">"
                  else:
                     yield "<" + propname + " xmlns='" + propns + "' >"
                     yield propvalue.encode('utf-8') 
                     yield "</"+propname+">"
               laststatus = propstatus
            if laststatus != '':
               yield "</D:prop>\n<D:status>HTTP/1.1 " + laststatus + "</D:status>\n</D:propstat>"         
         yield "</D:response>"
      yield "</D:multistatus>"      
      return 

   def doCOPY(self, environ, start_response):
      mappedrealm = environ['pyfileserver.mappedrealm']
      mappedpath = environ['pyfileserver.mappedpath']
      displaypath =  environ['pyfileserver.mappedURI']

      if not os.path.exists(mappedpath):
         raise HTTPRequestException(processrequesterrorhandler.HTTP_NOT_FOUND)         

      if 'HTTP_DEPTH' not in environ:
         environ['HTTP_DEPTH'] = 'infinity'
      if environ['HTTP_DEPTH'] != 'infinity':
         environ['HTTP_DEPTH'] = '0'
      
      
      if 'HTTP_DESTINATION' not in environ:
         raise HTTPRequestException(processreuesterrorhandler.HTTP_BAD_REQUEST)

      destrealm = environ['pyfileserver.destrealm']
      destpath = environ['pyfileserver.destpath']
      destdisplaypath = environ['pyfileserver.destURI']  
            
      destexists = os.path.exists(destpath)
      
      if mappedrealm != destrealm:
         #inter-realm copying not supported, since its not possible to authentication-wise
         raise HTTPRequestException(processrequesterrorhandler.HTTP_BAD_REQUEST)

      if mappedpath == destpath:
         raise HTTPRequestException(processrequesterrorhandler.HTTP_FORBIDDEN)
      
      ressrclist = websupportfuncs.getDepthActionList(mappedpath, displaypath, environ['HTTP_DEPTH'], True)
      resdestlist = websupportfuncs.getCopyDepthActionList(ressrclist, mappedpath, displaypath, destpath, destdisplaypath)
      
      if 'HTTP_OVERWRITE' not in environ:
         environ['HTTP_OVERWRITE'] = 'T'
      
      dictError = dict([])
      dictHidden = dict([])        
      for cpidx in range(0, len(ressrclist)):
         (filepath, filedisplaypath) = ressrclist[cpidx]     
         (destfilepath, destfiledisplaypath) = resdestlist[cpidx]     
         destparentpath = os.path.dirname(destfilepath)
         if destparentpath not in dictHidden:
            try:
               self.evaluateSingleHTTPConditionalsDoException( filepath, filedisplaypath, environ, start_response) 
               self.evaluateSingleIfConditionalDoException( filepath, filedisplaypath, environ, start_response)
               if os.path.exists(destfilepath) or self._lockmanager.isURLLocked(destfiledisplaypath) != None:
                  self.evaluateSingleIfConditionalDoException( destfilepath, destfiledisplaypath, environ, start_response, True)
               
               if not os.path.exists(destparentpath):
                  raise HTTPRequestException(processrequesterrorhandler.HTTP_CONFLICT)
               
               if not os.path.exists(destfilepath):
                  urlparentpath = websupportfuncs.getLevelUpURL(destfiledisplaypath)
                  if self._lockmanager.isURLLocked(urlparentpath):
                     self.evaluateSingleIfConditionalDoException( os.path.dirname(destfilepath), urlparentpath, environ, start_response, True)


               if environ['HTTP_OVERWRITE'] == 'F':
                  if os.path.exists(destfilepath):
                     raise HTTPRequestException(processrequesterrorhandler.HTTP_PRECONDITION_FAILED)
               else: #Overwrite = T
                  if os.path.exists(destfilepath):
                     actionList = websupportfuncs.getDepthActionList(destfilepath, destfiledisplaypath, 'infinity', False)
                     FdictHidden = dict([]) #hidden errors, ancestors of failed deletes         
                     # do DELETE with infinity
                     for (Ffilepath, Ffiledisplaypath) in actionList:         
                        if Ffilepath not in FdictHidden:
                           try:                           
                              if os.path.isdir(Ffilepath):
                                 os.rmdir(Ffilepath)
                              else:
                                 os.unlink(Ffilepath)
                              self._propertymanager.removeProperties(Ffiledisplaypath)               
                           except Exception:
                              pass
                           if os.path.exists(Ffilepath):
                              FdictHidden[os.path.dirname(Ffilepath)] = ''
                        else:
                           FdictHidden[os.path.dirname(Ffilepath)] = ''
                     if os.path.exists(Ffilepath):
                        raise HTTPRequestException(processrequesterrorhandler.HTTP_INTERNAL_ERROR) 
 
               if os.path.isdir(filepath):
                  os.mkdir(destfilepath)
               else:   
                  shutil.copy2(filepath, destfilepath)
               self._propertymanager.copyProperties(filedisplaypath, destfiledisplaypath)     
               self._lockmanager.checkLocksToAdd(destfiledisplaypath)

            except HTTPRequestException, e:
               dictError[destfiledisplaypath] = processrequesterrorhandler.interpretErrorException(e)
               dictHidden[destfilepath] = ''
            except Exception, e:
               pass   
            if not os.path.exists(destfilepath) and destfiledisplaypath not in dictError:
               dictError[destfiledisplaypath] = '500 Internal Server Error'    
               dictHidden[destfilepath] = ''           
         else:
            dictHidden[destfilepath] = ''

      if len(dictError) == 1 and destdisplaypath in dictError:
         start_response(dictError[destdisplaypath], [('Content-Length','0')])
         yield ''      
      elif len(dictError) > 0:
         start_response('207 Multi Status', [('Content-Length','0')])
         yield "<?xml version='1.0' ?>\n<D:multistatus xmlns:D='DAV:'>"
         for filedisplaypath in dictError.keys():
            yield "<D:response>\n<D:href>" + websupportfuncs.constructFullURL(filedisplaypath, environ) + "</D:href>"            
            yield "<D:status>HTTP/1.1 " + dictError[filedisplaypath] + "</D:status>\n</D:response>"            
         yield "</D:multistatus>"
      else:
         if destexists:
            start_response('204 No Content', [('Content-Length','0')])         
         else:
            start_response('201 Created', [('Content-Length','0')])
         yield ''
      return

   def doMOVE(self, environ, start_response):
      mappedrealm = environ['pyfileserver.mappedrealm']
      mappedpath = environ['pyfileserver.mappedpath']
      displaypath =  environ['pyfileserver.mappedURI']

      if not os.path.exists(mappedpath):
         raise HTTPRequestException(processrequesterrorhandler.HTTP_NOT_FOUND)         

      environ['HTTP_DEPTH'] = 'infinity'
      
      
      if 'HTTP_DESTINATION' not in environ:
         raise HTTPRequestException(processreuesterrorhandler.HTTP_BAD_REQUEST)
      
      destrealm = environ['pyfileserver.destrealm']
      destpath = environ['pyfileserver.destpath']
      destdisplaypath = environ['pyfileserver.destURI']      

      destexists = os.path.exists(destpath)
      
      if mappedrealm != destrealm:
         #inter-realm copying not supported, since its not possible to authentication-wise
         raise HTTPRequestException(processrequesterrorhandler.HTTP_BAD_REQUEST)

      if mappedpath == destpath:
         raise HTTPRequestException(processrequesterrorhandler.HTTP_FORBIDDEN)
      
      ressrclist = websupportfuncs.getDepthActionList(mappedpath, displaypath, environ['HTTP_DEPTH'], True)
      resdelsrclist = websupportfuncs.getDepthActionList(mappedpath, displaypath, environ['HTTP_DEPTH'], False)
      
      resdestlist = websupportfuncs.getCopyDepthActionList(ressrclist, mappedpath, displaypath, destpath, destdisplaypath)

      if 'HTTP_OVERWRITE' not in environ:
         environ['HTTP_OVERWRITE'] = 'T'
      
      dictError = dict([])
      dictHidden = dict([])        
      dictDoNotDel = dict([])
      for cpidx in range(0, len(ressrclist)):
         (filepath, filedisplaypath) = ressrclist[cpidx]     
         (destfilepath, destfiledisplaypath) = resdestlist[cpidx]     
         destparentpath = os.path.dirname(destfilepath)
         if destparentpath not in dictHidden:
            try:
               self.evaluateSingleHTTPConditionalsDoException( filepath, filedisplaypath, environ, start_response) 
               self.evaluateSingleIfConditionalDoException( filepath, filedisplaypath, environ, start_response, True)
               if os.path.exists(destfilepath) or self._lockmanager.isURLLocked(destfiledisplaypath) != None:
                  self.evaluateSingleIfConditionalDoException( destfilepath, destfiledisplaypath, environ, start_response, True)
               
               if not os.path.exists(destparentpath):
                  raise HTTPRequestException(processrequesterrorhandler.HTTP_CONFLICT)

               if not os.path.exists(filepath):
                  urlparentpath = websupportfuncs.getLevelUpURL(filedisplaypath)
                  if self._lockmanager.isURLLocked(urlparentpath):
                     self.evaluateSingleIfConditionalDoException( os.path.dirname(filepath), urlparentpath, environ, start_response, True)

               if not os.path.exists(destfilepath):
                  urlparentpath = websupportfuncs.getLevelUpURL(destfiledisplaypath)
                  if self._lockmanager.isURLLocked(urlparentpath):
                     self.evaluateSingleIfConditionalDoException( os.path.dirname(destfilepath), urlparentpath, environ, start_response, True)

               if environ['HTTP_OVERWRITE'] == 'F':
                  if os.path.exists(destfilepath):
                     raise HTTPRequestException(processrequesterrorhandler.HTTP_PRECONDITION_FAILED)
               else: #Overwrite = T
                  if os.path.exists(destfilepath):
                     actionList = websupportfuncs.getDepthActionList(destfilepath, destfiledisplaypath, 'infinity', False)
                     FdictHidden = dict([]) #hidden errors, ancestors of failed deletes         
                     # do DELETE with infinity
                     for (Ffilepath, Ffiledisplaypath) in actionList:         
                        if Ffilepath not in FdictHidden:
                           try:                           
                              if os.path.isdir(Ffilepath):
                                 os.rmdir(Ffilepath)
                              else:
                                 os.unlink(Ffilepath)
                              self._propertymanager.removeProperties(Ffiledisplaypath)               
                           except Exception:
                              pass
                           if os.path.exists(Ffilepath):
                              FdictHidden[os.path.dirname(Ffilepath)] = ''
                        else:
                           FdictHidden[os.path.dirname(Ffilepath)] = ''
                     if os.path.exists(Ffilepath):
                        raise HTTPRequestException(processrequesterrorhandler.HTTP_INTERNAL_ERROR) 
 
               if os.path.isdir(filepath):
                  os.mkdir(destfilepath)
               else:   
                  shutil.copy2(filepath, destfilepath)
               self._propertymanager.copyProperties(filedisplaypath, destfiledisplaypath)     
               self._lockmanager.checkLocksToAdd(destfiledisplaypath)

            except HTTPRequestException, e:
               dictError[destfiledisplaypath] = processrequesterrorhandler.interpretErrorException(e)
               dictHidden[destfilepath] = ''           
               dictDoNotDel[filepath]=''
            except Exception, e:
               pass   
            if not os.path.exists(destfilepath) and destfiledisplaypath not in dictError:
               dictError[destfiledisplaypath] = '500 Internal Server Error'    
               dictHidden[destfilepath] = ''           
               dictDoNotDel[filepath]=''
         else:
            dictHidden[destfilepath] = ''
            dictDoNotDel[filepath]=''

      # do DELETE with infinity on source
      FdictHidden = dict([]) #hidden errors, ancestors of failed deletes         
      for (Ffilepath, Ffiledisplaypath) in resdelsrclist:         
         if Ffilepath not in FdictHidden and Ffilepath not in dictDoNotDel:
            try:      
               if os.path.isdir(Ffilepath):
                  os.rmdir(Ffilepath)
               else:
                  os.unlink(Ffilepath)
               self._propertymanager.removeProperties(Ffiledisplaypath)               
               self._lockmanager.removeAllLocksFromURL(Ffiledisplaypath)
            except Exception:
               pass
            if os.path.exists(Ffilepath):
               FdictHidden[os.path.dirname(Ffilepath)] = ''
         else:
            FdictHidden[os.path.dirname(Ffilepath)] = ''

      if len(dictError) == 1 and destdisplaypath in dictError:
         start_response(dictError[destdisplaypath], [('Content-Length','0')])
         yield ''      
      elif len(dictError) > 0:
         start_response('207 Multi Status', [('Content-Length','0')])
         yield "<?xml version='1.0' ?>\n<D:multistatus xmlns:D='DAV:'>"
         for filedisplaypath in dictError.keys():
            yield "<D:response>\n<D:href>" + websupportfuncs.constructFullURL(filedisplaypath, environ) + "</D:href>"            
            yield "<D:status>HTTP/1.1 " + dictError[filedisplaypath] + "</D:status>\n</D:response>"            
         yield "</D:multistatus>"
      else:
         if destexists:
            start_response('204 No Content', [('Content-Length','0')])         
         else:
            start_response('201 Created', [('Content-Length','0')])
         yield ''
      return

   def doLOCK(self, environ, start_response):
      if 'HTTP_DEPTH' not in environ:
         environ['HTTP_DEPTH'] = 'infinity'
      if environ['HTTP_DEPTH'] != '0':
         environ['HTTP_DEPTH'] = 'infinity'    # only two acceptable
            
      mappedpath = environ['pyfileserver.mappedpath']
      displaypath =  environ['pyfileserver.mappedURI']

      contentlengthtoread = 0
      if 'CONTENT_LENGTH' in environ:
         if environ['CONTENT_LENGTH'].isdigit():
            contentlengthtoread = long(environ['CONTENT_LENGTH'])

      requestbody = ''
      if 'wsgi.input' in environ and contentlengthtoread > 0:
         inputstream = environ['wsgi.input']  
         readsize = BUF_SIZE
         if contentlengthtoread < BUF_SIZE:
            readsize = contentlengthtoread    
         readbuffer = inputstream.read(readsize)
         contentlengthtoread = contentlengthtoread - readsize
         requestbody = requestbody + readbuffer
         while len(readbuffer) != 0 and contentlengthtoread > 0:
            readsize = BUF_SIZE
            if contentlengthtoread < BUF_SIZE:
               readsize = contentlengthtoread    
            readbuffer = inputstream.read(readsize)
            contentlengthtoread = contentlengthtoread - readsize
            requestbody = requestbody + readbuffer
               
      if 'HTTP_TIMEOUT' not in environ:
         environ['HTTP_TIMEOUT'] = '' # reader function will return default
      timeoutsecs = propertylibrary.readTimeoutValueHeader(environ['HTTP_TIMEOUT'])         

      lockfailure = False
      dictStatus = dict([])

      if requestbody == '':
         #refresh lock only
         environ['HTTP_DEPTH'] = '0'
         reslist = [(mappedpath , displaypath)]
      
         self.evaluateSingleIfConditionalDoException( mappedpath, displaypath, environ, start_response, True)
         self.evaluateSingleHTTPConditionalsDoException( mappedpath, displaypath, environ, start_response)

         optlocklist = environ.get('pyfileserver.conditions.locklistcheck',[])
         for locklisttoken in optlocklist:
            self._lockmanager.refreshLock(locklisttoken,timeoutsecs)
            genlocktoken = locklisttoken

         dictStatus[displaypath] = "200 OK"      
      else:   

         try:
            doc = Sax2.Reader().fromString(requestbody)
         except Exception:
            raise HTTPRequestException(processrequesterrorhandler.HTTP_BAD_REQUEST)   
         liroot = doc.documentElement
         if liroot.namespaceURI != 'DAV:' or liroot.localName != 'lockinfo':
            raise HTTPRequestException(processrequesterrorhandler.HTTP_BAD_REQUEST)   

         locktype = 'write'         # various defaults
         lockscope = 'exclusive'
         lockowner = ''
         lockdepth = environ['HTTP_DEPTH']

         for linode in liroot.childNodes:
            if linode.namespaceURI == 'DAV:' and linode.localName == 'lockscope':
               for lsnode in linode.childNodes:
                  if lsnode.nodeType == xml.dom.Node.ELEMENT_NODE:
                     if lsnode.namespaceURI == 'DAV:' and lsnode.localName == 'exclusive': 
                        lockscope = 'exclusive' 
                     elif lsnode.namespaceURI == 'DAV:' and lsnode.localName == 'shared': 
                        lockscope = 'shared'
                     else:
                        raise HTTPRequestException(processrequesterrorhandler.HTTP_PRECONDITION_FAILED)
                     break               
            elif linode.namespaceURI == 'DAV:' and linode.localName == 'locktype':
               for ltnode in linode.childNodes:
                  if ltnode.nodeType == xml.dom.Node.ELEMENT_NODE:
                     if ltnode.namespaceURI == 'DAV:' and ltnode.localName == 'write': 
                        locktype = 'write'   # only type accepted
                     else:
                        raise HTTPRequestException(processrequesterrorhandler.HTTP_PRECONDITION_FAILED)
                     break
            elif linode.namespaceURI == 'DAV:' and linode.localName == 'owner':
               if len(linode.childNodes) == 1 and linode.firstChild.nodeType == xml.dom.Node.TEXT_NODE:
                  lockowner = linode.firstChild.nodeValue
               else:
                  lockownerstream = StringIO.StringIO()
                  for childnode in linode.childNodes:
                     xml.dom.ext.PrettyPrint(childnode, stream=lockownerstream)
                  lockowner = lockownerstream.getvalue()
                  lockownerstream.close()                        

         genlocktoken = self._lockmanager.generateLock(environ['pyfileserver.username'], locktype, lockscope, lockdepth, lockowner, websupportfuncs.constructFullURL(displaypath, environ), timeoutsecs)

         reslist = websupportfuncs.getDepthActionList(mappedpath, displaypath, environ['HTTP_DEPTH'], True)
         for (filepath, filedisplaypath) in reslist:
            try:
               self.evaluateSingleIfConditionalDoException(filepath, filedisplaypath, environ, start_response, False) # need not test for lock - since can try for shared lock
               self.evaluateSingleHTTPConditionalsDoException(filepath, filedisplaypath, environ, start_response)
               
               reschecklist = websupportfuncs.getDepthActionList(filepath, filedisplaypath, '1', True) 
               
               #lock over collection may not clash with locks of members   
               for (rescheckpath, rescheckdisplaypath) in reschecklist:
                  urllockscope = self._lockmanager.isURLLocked(rescheckdisplaypath)
                  if urllockscope == None or (urllockscope == 'shared' and lockscope == 'shared') :
                     pass
                  else:
                     raise HTTPRequestException(processrequesterrorhandler.HTTP_LOCKED)
               
               self._lockmanager.addURLToLock(filedisplaypath,genlocktoken)                  
               dictStatus[filedisplaypath] = "200 OK"            
            except HTTPRequestException, e:
               dictStatus[filedisplaypath] = processrequesterrorhandler.interpretErrorException(e)
               lockfailure = True   
            except Exception:
               raise
               dictStatus[filedisplaypath] = "500 Internal Server Error"
               lockfailure = True
         
         if lockfailure:
            self._lockmanager.deleteLock(genlocktoken)
      
      # done everything, now report on status
      if environ['HTTP_DEPTH'] == '0' or len(reslist) == 1:
         if lockfailure:
            respcode = dictStatus[displaypath]   
            start_response( respcode, [('Content-Length','0')])
            yield ''
            return
         else:                     
            start_response( "200 OK", [('Content-Type','text/xml'),('Lock-Token',genlocktoken)])
            yield "<?xml version=\'1.0\' ?>"
            yield "<D:prop xmlns:D=\'DAV:\'><D:lockdiscovery>"            
            (propvalue, propstatus) = propertylibrary.getProperty(self._propertymanager, self._lockmanager, mappedpath, displaypath, 'DAV:', 'lockdiscovery', self._etagprovider)   
            yield propvalue
            yield '</D:lockdiscovery></D:prop>'
            return
      else: 
         if lockfailure:
            start_response("207 Multistatus", [('Content-Type','text/xml')])
         else:
            start_response("200 OK", [('Content-Type','text/xml'),('Lock-Token',genlocktoken)])
         yield "<?xml version='1.0' ?>"
         yield "<D:multistatus xmlns:D='DAV:'>"
         for (filepath, filedisplaypath) in reslist:
            yield "<D:response>"
            yield "<D:href>" + websupportfuncs.constructFullURL(filedisplaypath, environ) + "</D:href>"
            if dictStatus[filedisplaypath] == '200 OK':
               yield "<D:propstat>"
               yield "<D:prop><D:lockdiscovery>"
               (propvalue, propstatus) = propertylibrary.getProperty(self._propertymanager, self._lockmanager, filepath, filedisplaypath, 'DAV:', 'lockdiscovery', self._etagprovider)   
               yield propvalue
               yield "</D:lockdiscovery></D:prop>"
               if lockfailure:
                  yield "<D:status>HTTP/1.1 424 Failed Dependency</D:status>"
               else:
                  yield "<D:status>HTTP/1.1 200 OK</D:status>"
               yield "</D:propstat>"
            else: 
               yield "<D:status>HTTP/1.1 " + dictStatus[filedisplaypath] + "</D:status>"
            yield "</D:response>"
         yield "</D:multistatus>"      
      return

   def doUNLOCK(self, environ, start_response):
      mappedpath = environ['pyfileserver.mappedpath']
      displaypath =  environ['pyfileserver.mappedURI']

      self.evaluateSingleIfConditionalDoException( mappedpath, displaypath, environ, start_response)
      self.evaluateSingleHTTPConditionalsDoException( mappedpath, displaypath, environ, start_response)
      
      if 'HTTP_LOCK_TOKEN' in environ:
         environ['HTTP_LOCK_TOKEN'] = environ['HTTP_LOCK_TOKEN'].strip('<>')
         if self._lockmanager.isURLLockedByToken(displaypath,environ['HTTP_LOCK_TOKEN']):
            if self._lockmanager.isTokenLockedByUser(environ['HTTP_LOCK_TOKEN'], environ['pyfileserver.username']):
               self._lockmanager.deleteLock(environ['HTTP_LOCK_TOKEN'])
               start_response('204 No Content',  [('Content-Length','0')])        
               yield ''      
               return

      raise HTTPRequestException(processrequesterrorhandler.HTTP_BAD_REQUEST)
      return


                
   def evaluateSingleIfConditionalDoException(self, mappedpath, displaypath, environ, start_response, checkLock = False):
      if 'HTTP_IF' not in environ:
         if checkLock:
            if self._lockmanager.isURLLocked(displaypath) != None:
               raise HTTPRequestException(processrequesterrorhandler.HTTP_LOCKED)            
         return
      if 'pyfileserver.conditions.if' not in environ:
         environ['pyfileserver.conditions.if'] = websupportfuncs.getIfHeaderDict(environ['HTTP_IF'])
      testDict = environ['pyfileserver.conditions.if']
      if os.path.exists(mappedpath):
         statresults = os.stat(mappedpath)
         lastmodified = statresults[stat.ST_MTIME]
         entitytag = self._etagprovider(mappedpath)         
         locktokenlist = self._lockmanager.getURLLocktokenListOfUser(displaypath,environ['pyfileserver.username'])
         isnewfile = False
      else:
         lastmodified = -1 # nonvalid modified time
         entitytag = '[]' # Non-valid entity tag
         locktokenlist = self._lockmanager.getURLLocktokenListOfUser(displaypath,environ['pyfileserver.username']) #null resources lock token not implemented yet
         isnewfile = True

      fullurl = websupportfuncs.constructFullURL(displaypath, environ)
      if not websupportfuncs.testIfHeaderDict(testDict, fullurl, locktokenlist, entitytag):
         raise HTTPRequestException(processrequesterrorhandler.HTTP_PRECONDITION_FAILED) 

      if checkLock and self._lockmanager.isURLLocked(displaypath) != None:
         hasValidLockToken = False
         for locktoken in locktokenlist:
            headurl = self._lockmanager.getLockProperty(locktoken, 'LOCKHEADURL')
            if websupportfuncs.testForLockTokenInIfHeaderDict(testDict, locktoken, fullurl, headurl):
               environ['pyfileserver.conditions.locklistcheck'] = [locktoken]
               hasValidLockToken = True
         if not hasValidLockToken:
            raise HTTPRequestException(processrequesterrorhandler.HTTP_LOCKED)
         

   def evaluateSingleHTTPConditionalsDoException(self, mappedpath, displaypath, environ, start_response):
      if 'HTTP_IF_MODIFIED_SINCE' in environ or 'HTTP_IF_UNMODIFIED_SINCE' in environ or 'HTTP_IF_MATCH' in environ or 'HTTP_IF_NONE_MATCH' in environ:
         pass
      else:
         return
      if os.path.exists(mappedpath):
         statresults = os.stat(mappedpath)
         lastmodified = statresults[stat.ST_MTIME]
         entitytag = self._etagprovider(mappedpath)         
         isnewfile = False
      else:
         lastmodified = -1 # nonvalid modified time
         entitytag = '[]' # Non-valid entity tag
         isnewfile = True      
      websupportfuncs.evaluateHTTPConditionals(lastmodified, entitytag, environ)
                
