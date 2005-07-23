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

from processrequesterrorhandler import ProcessRequestError
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
   def __init__(self, propertymanager, etagproviderfunc = etagprovider.getETag):
      self._propertymanager = propertymanager
      self._etagprovider = etagproviderfunc
      
   def __call__(self, environ, start_response):

      assert 'pyfileserver.mappedrealm' in environ
      assert 'pyfileserver.mappedpath' in environ
      assert 'pyfileserver.mappedURI' in environ
       
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
            raise ProcessRequestError(processrequesterrorhandler.HTTP_NOT_FOUND)               
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
      else:
         raise ProcessRequestError(processrequesterrorhandler.HTTP_METHOD_NOT_ALLOWED)


   def doPUT(self, environ, start_response):
      mappedpath = environ['pyfileserver.mappedpath']
      displaypath =  environ['pyfileserver.mappedURI']
      
      if os.path.isdir(mappedpath):
         raise ProcessRequestError(processrequesterrorhandler.HTTP_BAD_REQUEST)

      if not os.path.isdir(os.path.dirname(mappedpath)):
         raise ProcessRequestError(processrequesterrorhandler.HTTP_BAD_REQUEST)

      isnewfile = True
      if os.path.isfile(mappedpath):
         isnewfile = False
         statresults = os.stat(mappedpath)
         mode = statresults[stat.ST_MODE]      
         filesize = statresults[stat.ST_SIZE]
         lastmodified = statresults[stat.ST_MTIME]
         entitytag = self._etagprovider(mappedpath, environ)
      else:
         lastmodified = -1
         entitytag = self._etagprovider(mappedpath, environ)

      self.evaluateSingleIfConditionalDoException( mappedpath, displaypath, environ, start_response)
      self.evaluateSingleHTTPConditionalsDoException( mappedpath, displaypath, environ, start_response)

      websupportfuncs.evaluateHTTPConditionals(lastmodified, entitytag, environ, isnewfile)   

      ## Test for unsupported stuff

      if 'HTTP_CONTENT_ENCODING' in environ:
         raise ProcessRequestError(processrequesterrorhandler.HTTP_NOT_IMPLEMENTED)
         
      if 'HTTP_CONTENT_RANGE' in environ:
         raise ProcessRequestError(processrequesterrorhandler.HTTP_NOT_IMPLEMENTED)
      
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
      
      if isnewfile:
         start_response('201 Created', [('Content-Type', 'text/html'), ('Content-Length','0'), ('Date',httpdatehelper.getstrftime())])
      else:
         start_response('200 OK', [('Content-Type', 'text/html'), ('Content-Length','0'), ('Date',httpdatehelper.getstrftime())])
      
      return ['']
      
        
   def doOPTIONS(self, environ, start_response):
      mappedpath = environ['pyfileserver.mappedpath']
      if os.path.isdir(mappedpath):
         start_response('200 OK', [('Content-Type', 'text/html'), ('Content-Length','0'), ('Allow','OPTIONS HEAD GET PROPFIND PROPPATCH COPY MOVE'), ('DAV','1,2'), ('Date',httpdatehelper.getstrftime())])      
      elif os.path.isfile(mappedpath):
         start_response('200 OK', [('Content-Type', 'text/html'), ('Content-Length','0'), ('Allow','OPTIONS HEAD GET PUT DELETE PROPFIND PROPPATCH COPY MOVE'), ('DAV','1,2'), ('Allow-Ranges','bytes'), ('Date',httpdatehelper.getstrftime())])            
      elif os.path.isdir(os.path.dirname(mappedpath)):
         start_response('200 OK', [('Content-Type', 'text/html'), ('Content-Length','0'), ('Allow','OPTIONS PUT MKCOL'), ('DAV','1,2'), ('Date',httpdatehelper.getstrftime())])      
      else:
         raise ProcessRequestError(processrequesterrorhandler.HTTP_NOT_FOUND)         
      return [''];      




   def doGETHEADDirectory(self, environ, start_response):
      
      if environ['REQUEST_METHOD'] == 'HEAD':
         start_response('200 OK', [('Content-Type', 'text/html'), ('Date',httpdatehelper.getstrftime())])
         return ['']

      environ['HTTP_DEPTH'] = '0' #nothing else allowed
      mappedpath = environ['pyfileserver.mappedpath']
      mapdirprefix = environ['pyfileserver.mappedrealm']
      displaypath =  environ['pyfileserver.mappedURI']

      self.evaluateSingleIfConditionalDoException( mappedpath, displaypath, environ, start_response)
      self.evaluateSingleHTTPConditionalsDoException( mappedpath, displaypath, environ, start_response)
      
      trailer = ''
      if 'pyfileserver' in environ:
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
      return [proc_response]





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
      entitytag = self._etagprovider(mappedpath, environ)


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
            raise ProcessRequestError(processrequesterrorhandler.HTTP_RANGE_NOT_SATISFIABLE)

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
            raise ProcessRequestError(processrequesterrorhandler.HTTP_MEDIATYPE_NOT_SUPPORTED)

      environ['HTTP_DEPTH'] = '0' #nothing else allowed
      mappedpath = environ['pyfileserver.mappedpath']
      displaypath =  environ['pyfileserver.mappedURI']
      
      self.evaluateSingleIfConditionalDoException( mappedpath, displaypath, environ, start_response)
      self.evaluateSingleHTTPConditionalsDoException( mappedpath, displaypath, environ, start_response)
      
      if os.path.exists(mappedpath):
         raise ProcessRequestError(processrequesterrorhandler.HTTP_METHOD_NOT_ALLOWED)         
      parentdir = os.path.dirname(mappedpath)
      
      if not os.path.isdir(parentdir):
         raise ProcessRequestError(processrequesterrorhandler.HTTP_CONFLICT)          
      try:   
         os.mkdir(mappedpath)
      except Exception:
         pass
      if os.path.exists(mappedpath):
         start_response("201 Created", [('Content-Length',0)])
      else:
         start_response("200 OK", [('Content-Length',0)])
      return['']

   def doDELETE(self, environ, start_response):
      mappedpath = environ['pyfileserver.mappedpath']
      displaypath =  environ['pyfileserver.mappedURI']

      if not os.path.exists(mappedpath):
         raise ProcessRequestError(processrequesterrorhandler.HTTP_NOT_FOUND)         

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
               self.evaluateSingleIfConditionalDoException( filepath, filedisplaypath, environ, start_response)
               self.evaluateSingleHTTPConditionalsDoException( filepath, filedisplaypath, environ, start_response)

               if os.path.isdir(filepath):
                  os.rmdir(filepath)
               else:
                  os.unlink(filepath)
               self._propertymanager.removeProperties(filedisplaypath)
            except ProcessRequestError, e:
               evalue = e.value
               if evalue in processrequesterrorhandler.ERROR_DESCRIPTIONS:
                  dictError[filedisplaypath] = processrequesterrorhandler.ERROR_DESCRIPTIONS[evalue]
               else:
                  dictError[filedisplaypath] = str(evalue)
               dictHidden[os.path.dirname(filepath)] = ''
            except Exception:
               pass
            if os.path.exists(filepath) and filedisplaypath not in dictError:
               dictError[filedisplaypath] = '500 Internal Server Error'
               dictHidden[os.path.dirname(filepath)] = ''
         else:
            dictHidden[os.path.dirname(filepath)] = ''

      if len(dictError) == 1 and mappedpath in dictError:
         start_response(dictError[mappedpath], [('Content-Length','0')])
         yield ''      
      elif len(dictError) > 0:
         start_response('207 Multi Status', [('Content-Length','0')])
         yield "<?xml version='1.0' ?>\n<multistatus xmlns='DAV:'>"
         for filedisplaypath in dictError.keys():
            yield "<response>\n<href>" + websupportfuncs.constructFullURL(filedisplaypath, environ) + "</href>"            
            yield "<status>HTTP/1.1 " + dictError[filedisplaypath] + "</status>\n</response>"            
         yield "</multistatus>"
      else:
         start_response('204 No Content', [('Content-Length','0')])
         yield ''
      return


   def doPROPPATCH(self, environ, start_response):

      print self._propertymanager.getString()

      environ['HTTP_DEPTH'] = '0' #nothing else allowed
      mappedpath = environ['pyfileserver.mappedpath']
      displaypath =  environ['pyfileserver.mappedURI']
      
      self.evaluateSingleIfConditionalDoException( mappedpath, displaypath, environ, start_response)
      self.evaluateSingleHTTPConditionalsDoException( mappedpath, displaypath, environ, start_response)

      contentlengthtoread = 0
      if 'CONTENT_LENGTH' in environ:
         if environ['CONTENT_LENGTH'].isdigit():
            contentlengthtoread = long(environ['CONTENT_LENGTH'])

      requestbody = ''
      if 'wsgi.input' in environ:
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

      print requestbody
                     
      try:
         doc = Sax2.Reader().fromString(requestbody)
      except Exception:
         raise ProcessRequestError(processrequesterrorhandler.HTTP_BAD_REQUEST)   
      pproot = doc.documentElement
      if pproot.namespaceURI != 'DAV:' or pproot.localName != 'propertyupdate':
         raise ProcessRequestError(processrequesterrorhandler.HTTP_BAD_REQUEST)   

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
         yield "<?xml version='1.0' ?>\n<multistatus xmlns='DAV:'>\n<response>"
         yield "<href>" + websupportfuncs.constructFullURL(displaypath, environ) + "</href>"    
         laststatus = ''
         for (propns, propname , propmethod , propvalue) in propupdatelist:
            propstatus = propertylibrary.writeProperty(self._propertymanager, mappedpath, displaypath, propns, propname , propmethod , propvalue, True)
            if laststatus == '':
               yield "<propstat>\n<prop>"                                  
            if propstatus != laststatus and laststatus != '':
               yield "</prop>\n<status>HTTP/1.1 " + laststatus + "</status>\n</propstat>\n<propstat>\n<prop>" 
            if propns == 'DAV:':
               yield "<" + propname + "/>"
            else:
               yield "<" + propname + " xmlns='" + propns + "' />"
            laststatus = propstatus
         if laststatus != '':
            yield "</prop>\n<status>HTTP/1.1 " + laststatus + "</status>\n</propstat>"         
         yield "</response>\n</multistatus>"
      else:
         yield "<?xml version='1.0' ?>\n<multistatus xmlns='DAV:'>\n<response>"
         yield "<href>" + websupportfuncs.constructFullURL(displaypath, environ) + "</href>"    
         laststatus = ''
         for (propns, propname, propstatus) in writeresultlist:
            if propstatus == '200 OK':
               propstatus = '424 Failed Dependency'
            if laststatus == '':
               yield "<propstat>\n<prop>"                                  
            if propstatus != laststatus and laststatus != '':
               yield "</prop>\n<status>HTTP/1.1 " + laststatus + "</status>\n</propstat>\n<propstat>\n<prop>" 
            if propns == 'DAV:':
               yield "<" + propname + "/>"
            else:
               yield "<" + propname + " xmlns='" + propns + "' />"
            laststatus = propstatus
         if laststatus != '':
            yield "</prop>\n<status>HTTP/1.1 " + laststatus + "</status>\n</propstat>"         
         yield "</response>\n</multistatus>"
      return
   
   # does not yet support If and If HTTP Conditions   
   def doPROPFIND(self, environ, start_response):

      print self._propertymanager.getString()

      if 'HTTP_DEPTH' not in environ:
         environ['HTTP_DEPTH'] = '0'
      mappedpath = environ['pyfileserver.mappedpath']
      displaypath =  environ['pyfileserver.mappedURI']
                  
      contentlengthtoread = 0
      if 'CONTENT_LENGTH' in environ:
         if environ['CONTENT_LENGTH'].isdigit():
            contentlengthtoread = long(environ['CONTENT_LENGTH'])

      requestbody = ''
      if 'wsgi.input' in environ:
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
         requestbody = '<DAV:propfind><DAV:allprop/></DAV:propfind>'
      
      print requestbody
         
      try:
         doc = Sax2.Reader().fromString(requestbody)
      except Exception:
         raise ProcessRequestError(processrequesterrorhandler.HTTP_BAD_REQUEST)   
      pfroot = doc.documentElement
      if pfroot.namespaceURI != 'DAV:' or pfroot.localName != 'propfind':
         raise ProcessRequestError(processrequesterrorhandler.HTTP_BAD_REQUEST)   

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
      yield "<multistatus xmlns='DAV:'>"
      for (respath , resdisplayname) in reslist:
         yield "<response>"
         yield "<href>" + websupportfuncs.constructFullURL(resdisplayname, environ) + "</href>"    

         if propFindMode == 1 or propFindMode == 2:
            propList = propertylibrary.getApplicablePropertyNames(self._propertymanager, respath, resdisplayname)
            
         if propFindMode == 2:
            yield "<propstat>\n<prop>"
            for (propns, propname) in propList:
               if propns == 'DAV:':
                  yield "<" + propname + "/>"
               else:
                  yield "<" + propname + " xmlns='" + propns + "'/>"
            yield "</prop>\n<status>HTTP/1.1 200 OK</status>\n</propstat>"
         else:
            laststatus = ''
            for (propns, propname) in propList:
               try:
#                  self.evaluateSingleIfConditionalDoException( filepath, filedisplaypath, environ, start_response)
#                  self.evaluateSingleHTTPConditionalsDoException( filepath, filedisplaypath, environ, start_response)
                  (propvalue, propstatus) = propertylibrary.getProperty(self._propertymanager, respath, resdisplayname, propns, propname, self._etagprovider)   
               except ProcessRequestError, e:
                  evalue = e.value
                  propvalue = ''
                  if evalue in processrequesterrorhandler.ERROR_DESCRIPTIONS:
                     propstatus = processrequesterrorhandler.ERROR_DESCRIPTIONS[evalue]
                  else:
                     propstatus = str(evalue)
               if laststatus == '':
                  yield "<propstat>\n<prop>"                                  
               if propstatus != laststatus and laststatus != '':
                  yield "</prop>\n<status>HTTP/1.1 " + laststatus + "</status>\n</propstat>\n<propstat>\n<prop>" 
               if propvalue == None:
                  propvalue = '';               
               if propns == 'DAV:':
                  yield "<" + propname + ">"
                  yield propvalue.encode('utf-8') 
                  yield "</"+propname+">"
               else:
                  yield "<" + propname + " xmlns='" + propns + "' >"
                  yield propvalue.encode('utf-8') 
                  yield "</"+propname+">"
               laststatus = propstatus
            if laststatus != '':
               yield "</prop>\n<status>HTTP/1.1 " + laststatus + "</status>\n</propstat>"         
         yield "</response>"
      yield "</multistatus>"      
      return 

   def doCOPY(self, environ, start_response):
      mappedrealm = environ['pyfileserver.mappedrealm']
      mappedpath = environ['pyfileserver.mappedpath']
      displaypath =  environ['pyfileserver.mappedURI']

      if not os.path.exists(mappedpath):
         raise ProcessRequestError(processrequesterrorhandler.HTTP_NOT_FOUND)         

      if 'HTTP_DEPTH' not in environ:
         environ['HTTP_DEPTH'] = 'infinity'
      if environ['HTTP_DEPTH'] != 'infinity':
         environ['HTTP_DEPTH'] = '0'
      
      
      if 'HTTP_DESTINATION' not in environ:
         raise ProcessRequestError(processreuesterrorhandler.HTTP_BAD_REQUEST)
      desturl = websupportfuncs.getRelativeURL(environ['HTTP_DESTINATION'], environ)
      (destrealm, destpath, destdisplaypath) = requestresolver.resolveRealmURI(environ['pyfileserver.config']['config_mapping'], desturl)
      
      destexists = os.path.exists(destpath)
      
      if mappedrealm != destrealm:
         #inter-realm copying not supported, since its not possible to authentication-wise
         raise ProcessRequestError(processrequesterrorhandler.HTTP_BAD_REQUEST)

      if mappedpath == destpath:
         raise ProcessRequestError(processrequesterrorhandler.HTTP_FORBIDDEN)
      
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
               self.evaluateSingleIfConditionalDoException( destfilepath, destfiledisplaypath, environ, start_response)
               
               if not os.path.exists(destparentpath):
                  raise ProcessRequestError(processrequesterrorhandler.HTTP_CONFLICT)

               if environ['HTTP_OVERWRITE'] == 'F':
                  if os.path.exists(destfilepath):
                     raise ProcessRequestError(processrequesterrorhandler.HTTP_PRECONDITION_FAILED)
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
                        raise ProcessRequestError(processrequesterrorhandler.HTTP_INTERNAL_ERROR) 
 
               if os.path.isdir(filepath):
                  os.mkdir(destfilepath)
               else:   
                  shutil.copy2(filepath, destfilepath)
               self._propertymanager.copyProperties(filedisplaypath, destfiledisplaypath)     

            except ProcessRequestError, e:
               evalue = e.value
               if evalue in processrequesterrorhandler.ERROR_DESCRIPTIONS:
                  dictError[destfiledisplaypath] = processrequesterrorhandler.ERROR_DESCRIPTIONS[evalue]
                  dictHidden[destfilepath] = ''           
               else:
                  dictError[destfiledisplaypath] = str(evalue)
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
         yield "<?xml version='1.0' ?>\n<multistatus xmlns='DAV:'>"
         for filedisplaypath in dictError.keys():
            yield "<response>\n<href>" + websupportfuncs.constructFullURL(filedisplaypath, environ) + "</href>"            
            yield "<status>HTTP/1.1 " + dictError[filedisplaypath] + "</status>\n</response>"            
         yield "</multistatus>"
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
         raise ProcessRequestError(processrequesterrorhandler.HTTP_NOT_FOUND)         

      environ['HTTP_DEPTH'] = 'infinity'
      
      
      if 'HTTP_DESTINATION' not in environ:
         raise ProcessRequestError(processreuesterrorhandler.HTTP_BAD_REQUEST)
      desturl = websupportfuncs.getRelativeURL(environ['HTTP_DESTINATION'], environ)
      (destrealm, destpath, destdisplaypath) = requestresolver.resolveRealmURI(environ['pyfileserver.config']['config_mapping'], desturl)
      
      destexists = os.path.exists(destpath)
      
      if mappedrealm != destrealm:
         #inter-realm copying not supported, since its not possible to authentication-wise
         raise ProcessRequestError(processrequesterrorhandler.HTTP_BAD_REQUEST)

      if mappedpath == destpath:
         raise ProcessRequestError(processrequesterrorhandler.HTTP_FORBIDDEN)
      
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
               self.evaluateSingleIfConditionalDoException( filepath, filedisplaypath, environ, start_response)
               self.evaluateSingleIfConditionalDoException( destfilepath, destfiledisplaypath, environ, start_response)
               
               if not os.path.exists(destparentpath):
                  raise ProcessRequestError(processrequesterrorhandler.HTTP_CONFLICT)

               if environ['HTTP_OVERWRITE'] == 'F':
                  if os.path.exists(destfilepath):
                     raise ProcessRequestError(processrequesterrorhandler.HTTP_PRECONDITION_FAILED)
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
                        raise ProcessRequestError(processrequesterrorhandler.HTTP_INTERNAL_ERROR) 
 
               if os.path.isdir(filepath):
                  os.mkdir(destfilepath)
               else:   
                  shutil.copy2(filepath, destfilepath)
               self._propertymanager.copyProperties(filedisplaypath, destfiledisplaypath)     

            except ProcessRequestError, e:
               evalue = e.value
               if evalue in processrequesterrorhandler.ERROR_DESCRIPTIONS:
                  dictError[destfiledisplaypath] = processrequesterrorhandler.ERROR_DESCRIPTIONS[evalue]
               else:
                  dictError[destfiledisplaypath] = str(evalue)
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
         yield "<?xml version='1.0' ?>\n<multistatus xmlns='DAV:'>"
         for filedisplaypath in dictError.keys():
            yield "<response>\n<href>" + websupportfuncs.constructFullURL(filedisplaypath, environ) + "</href>"            
            yield "<status>HTTP/1.1 " + dictError[filedisplaypath] + "</status>\n</response>"            
         yield "</multistatus>"
      else:
         if destexists:
            start_response('204 No Content', [('Content-Length','0')])         
         else:
            start_response('201 Created', [('Content-Length','0')])
         yield ''
      return



   def evaluateSingleIfConditional(self, mappedpath, displaypath, environ, start_response):
      if 'HTTP_IF' not in environ:
         return
      if 'pyfileserver.conditions.if' not in environ:
         environ['pyfileserver.conditions.if'] = web.supportfuncs.getIfHeaderDict(environ['HTTP_IF'])
      testDict = environ['pyfileserver.conditions.if']
      if os.path.exists(mappedpath):
         statresults = os.stat(mappedpath)
         lastmodified = statresults[stat.ST_MTIME]
         entitytag = self._etagprovider(mappedpath, environ)         
         locktokenlist = [] # not implemented yet
         isnewfile = False
      else:
         lastmodified = -1 # nonvalid modified time
         entitytag = '[]' # Non-valid entity tag
         locktokenlist = [] #non-valid locktoken
         isnewfile = True
      if not websupportfuncs.testIfHeaderDict(testDict, displaypath, locktokenlist, entitytag):
         return '412 Precondition Failed'
      return '200 OK'   
#         raise ProcessRequestError(processrequesterrorhandler.HTTP_PRECONDITION_FAILED) 

   def evaluateSingleHTTPConditionals(self, mappedpath, displaypath, environ, start_response):
      if 'HTTP_IF_MODIFIED_SINCE' in environ or 'HTTP_IF_UNMODIFIED_SINCE' in environ or 'HTTP_IF_MATCH' in environ or 'HTTP_IF_NONE_MATCH' in environ:
         pass
      else:
         return
      if os.path.exists(mappedpath):
         statresults = os.stat(mappedpath)
         lastmodified = statresults[stat.ST_MTIME]
         entitytag = self._etagprovider(mappedpath, environ)         
         isnewfile = False
      else:
         lastmodified = -1 # nonvalid modified time
         entitytag = '[]' # Non-valid entity tag
         isnewfile = True      
      return websupportfuncs.evaluateHTTPConditionalsWithoutExceptions(lastmodified, entitytag, environ)
                

   def evaluateSingleIfConditionalDoException(self, mappedpath, displaypath, environ, start_response):
      if 'HTTP_IF' not in environ:
         return
      if 'pyfileserver.conditions.if' not in environ:
         environ['pyfileserver.conditions.if'] = web.supportfuncs.getIfHeaderDict(environ['HTTP_IF'])
      testDict = environ['pyfileserver.conditions.if']
      if os.path.exists(mappedpath):
         statresults = os.stat(mappedpath)
         lastmodified = statresults[stat.ST_MTIME]
         entitytag = self._etagprovider(mappedpath, environ)         
         locktokenlist = [] # not implemented yet
         isnewfile = False
      else:
         lastmodified = -1 # nonvalid modified time
         entitytag = '[]' # Non-valid entity tag
         locktokenlist = [] #non-valid locktoken
         isnewfile = True
      if not websupportfuncs.testIfHeaderDict(testDict, displaypath, locktokenlist, entitytag):
         raise ProcessRequestError(processrequesterrorhandler.HTTP_PRECONDITION_FAILED) 

   def evaluateSingleHTTPConditionalsDoException(self, mappedpath, displaypath, environ, start_response):
      if 'HTTP_IF_MODIFIED_SINCE' in environ or 'HTTP_IF_UNMODIFIED_SINCE' in environ or 'HTTP_IF_MATCH' in environ or 'HTTP_IF_NONE_MATCH' in environ:
         pass
      else:
         return
      if os.path.exists(mappedpath):
         statresults = os.stat(mappedpath)
         lastmodified = statresults[stat.ST_MTIME]
         entitytag = self._etagprovider(mappedpath, environ)         
         isnewfile = False
      else:
         lastmodified = -1 # nonvalid modified time
         entitytag = '[]' # Non-valid entity tag
         isnewfile = True      
      websupportfuncs.evaluateHTTPConditionals(lastmodified, entitytag, environ)
                


   def evaluateIfConditional(self, actionList, environ, start_response):
      if 'HTTP_IF' not in environ:
         return
      if 'pyfileserver.conditions.if' not in environ:
         environ['pyfileserver.conditions.if'] = web.supportfuncs.getIfHeaderDict(environ['HTTP_IF'])
      testDict = environ['pyfileserver.conditions.if']
            
      for (mappedpath, displaypath) in actionList:
         if os.path.exists(mappedpath):
            statresults = os.stat(mappedpath)
            lastmodified = statresults[stat.ST_MTIME]
            entitytag = self._etagprovider(mappedpath, environ)         
            locktokenlist = [] # not implemented yet
            isnewfile = False
         else:
            lastmodified = -1 # nonvalid modified time
            entitytag = '[]' # Non-valid entity tag
            locktokenlist = [] #non-valid locktoken
            isnewfile = True
         if not websupportfuncs.testIfHeaderDict(testDict, displaypath, locktokenlist, entitytag):
            raise ProcessRequestError(processrequesterrorhandler.HTTP_PRECONDITION_FAILED) 

   def evaluateHTTPConditionals(self, mappedpath, displaypath, environ, start_response):
      if 'HTTP_IF_MODIFIED_SINCE' in environ or 'HTTP_IF_UNMODIFIED_SINCE' in environ or 'HTTP_IF_MATCH' in environ or 'HTTP_IF_NONE_MATCH' in environ:
         pass
      else:
         return
      if os.path.exists(mappedpath):
         statresults = os.stat(mappedpath)
         lastmodified = statresults[stat.ST_MTIME]
         entitytag = self._etagprovider(mappedpath, environ)         
         isnewfile = False
      else:
         lastmodified = -1 # nonvalid modified time
         entitytag = '[]' # Non-valid entity tag
         isnewfile = True      
      websupportfuncs.evaluateHTTPConditionals(lastmodified, entitytag, environ)   
