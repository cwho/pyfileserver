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

import httpdatehelper
import etagprovider

# CONSTANTS
URL_SEP = '/'
BUFFER_SIZE = 8192


# Range Specifiers
reByteRangeSpecifier = re.compile("(([0-9]+)\-([0-9]*))")
reSuffixByteRangeSpecifier = re.compile("(\-([0-9]+))")

class RequestServer(object):
   def __init__(self, infoHeader = None, etagproviderfunc = etagprovider.getETag):
      self._infoHeader = infoHeader
      self._etagprovider = etagproviderfunc
      
   def __call__(self, environ, start_response):

      self._srvcfg = environ['pyfileserver.config']
      assert 'pyfileserver.mappedrealm' in environ
      assert 'pyfileserver.mappedrealmrelativeurl' in environ
      assert 'pyfileserver.mappedrealmlocaldir' in environ
       
      requestmethod =  environ['REQUEST_METHOD'].upper()   

      mapdirprefix = environ['pyfileserver.mappedrealm']
      relativepath = environ['pyfileserver.mappedrealmrelativeurl']
      localheadpath =  environ['pyfileserver.mappedrealmlocaldir']

      relativepath = relativepath.replace(URL_SEP, os.sep)
   
      if relativepath.endswith(os.sep):
         relativepath = relativepath[:-len(os.sep)] # remove suffix os.sep since it causes error (SyntaxError) with os.path functions
   
      normrelativepath = ''
      if relativepath != '':          # avoid adding of .s
         normrelativepath = os.path.normpath(relativepath)   
         
      # Note: Firefox apparently resolves .. and . on client side before sending it to server. IE doesnt.        
      if self._srvcfg['AllowRelativePaths'] == 0:
         if normrelativepath != relativepath:
            raise ProcessRequestError(processrequesterrorhandler.HTTP_FORBIDDEN)
      
      mappedpath = localheadpath + os.sep + normrelativepath
      
      if(normrelativepath != ""):
         displaypath = mapdirprefix + normrelativepath.replace(os.sep, URL_SEP)
      else:
         displaypath = mapdirprefix 
      
      if os.path.isdir(mappedpath): 
         displaypath = displaypath + URL_SEP
      
      if (requestmethod == 'GET' or requestmethod == 'POST' or requestmethod == 'HEAD'):
         if os.path.isdir(mappedpath): 
            return self.doGETPOSTHEADDirectory(mappedpath, displaypath, normrelativepath, requestmethod, environ, start_response)
         elif os.path.isfile(mappedpath):
            return self.doGETPOSTHEADFile(mappedpath, requestmethod, environ, start_response)
         else:
            raise self.ProcessRequestError(processrequesterrorhandler.HTTP_NOT_FOUND)               
      elif requestmethod == 'PUT':
         return doPUTFile(mappedpath, environ, start_response)
      elif requestmethod == 'DELETE':
         return doDELETEFile(mappedpath, environ, start_response)
      elif requestmethod == 'OPTION':
         return doOPTIONSSpecific(mappedpath, environ, start_response)
      elif requestmethod == 'TRACE':
         return doTRACE(mappedpath, environ, start_response)
      else:
         raise self.ProcessRequestError(processrequesterrorhandler.HTTP_METHOD_NOT_ALLOWED)
      

   #TRACE pending, but not essential in this case
   def doTRACE(self, mappedpath, environ, start_response):
      raise ProcessRequestError(processrequesterrorhandler.HTTP_NOT_IMPLEMENTED)

   def doDELETEFile(self, mappedpath, environ, start_response):
      if not os.path.isfile(mappedpath):
         raise ProcessRequestError(processrequesterrorhandler.HTTP_NOT_FOUND)

      statresults = os.stat(mappedpath)
      mode = statresults[stat.ST_MODE]      
      filesize = statresults[stat.ST_SIZE]
      lastmodified = statresults[stat.ST_MTIME]
      entitytag = self._etagprovider(mappedpath, environ)

      ## Conditions

      # An HTTP/1.1 origin server, upon receiving a conditional request that includes both a Last-Modified date
      # (e.g., in an If-Modified-Since or If-Unmodified-Since header field) and one or more entity tags (e.g., 
      # in an If-Match, If-None-Match, or If-Range header field) as cache validators, MUST NOT return a response 
      # status of 304 (Not Modified) unless doing so is consistent with all of the conditional header fields in 
      # the request.

      if 'HTTP_IF_MATCH' in environ:
         ifmatchlist = environ['HTTP_IF_MATCH'].split(",")
         for ifmatchtag in ifmatchlist:
            ifmatchtag = ifmatchtag.strip(" \"\t")
            if ifmatchtag == entitytag or ifmatchtag == '*':
               break   
            raise ProcessRequestError(processrequesterrorhandler.HTTP_PRECONDITION_FAILED)
         
      
      # If-None-Match 
      # If none of the entity tags match, then the server MAY perform the requested method as if the 
      # If-None-Match header field did not exist, but MUST also ignore any If-Modified-Since header field
      # (s) in the request. That is, if no entity tags match, then the server MUST NOT return a 304 (Not Modified) 
      # response.
      ignoreifmodifiedsince = False         
      if 'HTTP_IF_NONE_MATCH' in environ:         
         ifmatchlist = environ['HTTP_IF_NONE_MATCH'].split(",")
         for ifmatchtag in ifmatchlist:
            ifmatchtag = ifmatchtag.strip(" \"\t")
            if ifmatchtag == entitytag or ifmatchtag == '*':
               raise ProcessRequestError(processrequesterrorhandler.HTTP_PRECONDITION_FAILED)
         ignoreifmodifiedsince = True

      if 'HTTP_IF_UNMODIFIED_SINCE' in environ:
         ifunmodtime = httpdatehelper.getsecstime(environ['HTTP_IF_UNMODIFIED_SINCE'])
         if ifunmodtime:
            if ifunmodtime <= lastmodified:
               raise ProcessRequestError(processrequesterrorhandler.HTTP_PRECONDITION_FAILED)

      if 'HTTP_IF_MODIFIED_SINCE' in environ and not ignoreifmodifiedsince:
         ifmodtime = httpdatehelper.getsecstime(environ['HTTP_IF_MODIFIED_SINCE'])
         if ifmodtime:
            if ifmodtime > lastmodified:
               raise ProcessRequestError(processrequesterrorhandler.HTTP_NOT_MODIFIED)

      os.unlink(mappedpath)

      start_response('204 No Content', [('Content-Type', 'text/html'), ('Content-Length','0'), ('Date',httpdatehelper.getstrftime())])

      return ['']

      

   def doPUTFile(self, mappedpath, environ, start_response):
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

      ## Conditions

      # An HTTP/1.1 origin server, upon receiving a conditional request that includes both a Last-Modified date
      # (e.g., in an If-Modified-Since or If-Unmodified-Since header field) and one or more entity tags (e.g., 
      # in an If-Match, If-None-Match, or If-Range header field) as cache validators, MUST NOT return a response 
      # status of 304 (Not Modified) unless doing so is consistent with all of the conditional header fields in 
      # the request.

      if 'HTTP_IF_MATCH' in environ:
         if isnewfile:
            raise ProcessRequestError(processrequesterrorhandler.HTTP_PRECONDITION_FAILED)
         else:
            ifmatchlist = environ['HTTP_IF_MATCH'].split(",")
            for ifmatchtag in ifmatchlist:
               ifmatchtag = ifmatchtag.strip(" \"\t")
               if ifmatchtag == entitytag or ifmatchtag == '*':
                  break   
               raise ProcessRequestError(processrequesterrorhandler.HTTP_PRECONDITION_FAILED)
         
      
      # If-None-Match 
      # If none of the entity tags match, then the server MAY perform the requested method as if the 
      # If-None-Match header field did not exist, but MUST also ignore any If-Modified-Since header field
      # (s) in the request. That is, if no entity tags match, then the server MUST NOT return a 304 (Not Modified) 
      # response.
      ignoreifmodifiedsince = False         
      if 'HTTP_IF_NONE_MATCH' in environ:         
         if isnewfile:
            ignoreifmodifiedsince = True
         else:
            ifmatchlist = environ['HTTP_IF_NONE_MATCH'].split(",")
            for ifmatchtag in ifmatchlist:
               ifmatchtag = ifmatchtag.strip(" \"\t")
               if ifmatchtag == entitytag or ifmatchtag == '*':
                  raise ProcessRequestError(processrequesterrorhandler.HTTP_PRECONDITION_FAILED)
            ignoreifmodifiedsince = True

      if not isnewfile and 'HTTP_IF_UNMODIFIED_SINCE' in environ:
         ifunmodtime = httpdatehelper.getsecstime(environ['HTTP_IF_UNMODIFIED_SINCE'])
         if ifunmodtime:
            if ifunmodtime <= lastmodified:
               raise ProcessRequestError(processrequesterrorhandler.HTTP_PRECONDITION_FAILED)

      if not isnewfile and 'HTTP_IF_MODIFIED_SINCE' in environ and not ignoreifmodifiedsince:
         ifmodtime = httpdatehelper.getsecstime(environ['HTTP_IF_MODIFIED_SINCE'])
         if ifmodtime:
            if ifmodtime > lastmodified:
               raise ProcessRequestError(processrequesterrorhandler.HTTP_NOT_MODIFIED)

      ## Test for unsupported stuff

      if 'HTTP_CONTENT_ENCODING' in environ:
         raise ProcessRequestError(processrequesterrorhandler.HTTP_NOT_IMPLEMENTED)
         
      if 'HTTP_CONTENT_RANGE' in environ:
         raise ProcessRequestError(processrequesterrorhandler.HTTP_NOT_IMPLEMENTED)
      
      ## Start Content Processing
      
      contentlength = -1
      if 'HTTP_CONTENT_LENGTH' in environ:
         if isdigit(environ['HTTP_CONTENT_LENGTH']):
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
      
      
   def doOPTIONSGeneric(self, environ, start_response):
      start_response('200 OK', [('Content-Type', 'text/html'), ('Content-Length','0'), ('Date',httpdatehelper.getstrftime())])
      return ['']      
   
   def doOPTIONSSpecific(self, mappedpath, environ, start_response):
      if os.path.isdir(mappedpath):
         start_response('200 OK', [('Content-Type', 'text/html'), ('Content-Length','0'), ('Allow','OPTIONS HEAD GET POST'), ('Date',httpdatehelper.getstrftime())])      
      elif os.path.isfile(mappedpath):
         start_response('200 OK', [('Content-Type', 'text/html'), ('Content-Length','0'), ('Allow','OPTIONS HEAD GET POST PUT DELETE'), ('Allow-Ranges','bytes'), ('Date',httpdatehelper.getstrftime())])            
      elif os.path.isdir(os.path.dirname(mappedpath)):
         start_response('200 OK', [('Content-Type', 'text/html'), ('Content-Length','0'), ('Allow','OPTIONS PUT'), ('Date',httpdatehelper.getstrftime())])      
      else:
         raise ProcessRequestError(processrequesterrorhandler.HTTP_NOT_FOUND)         
      return '';      



   def doGETPOSTHEADDirectory(self, mappedpath, displaypath, normrelativepath, requestmethod, environ, start_response):
      if not os.path.isdir(mappedpath):
         raise ProcessRequestError(processrequesterrorhandler.HTTP_NOT_FOUND)

      if requestmethod == 'HEAD':
         start_response('200 OK', [('Content-Type', 'text/html'), ('Date',httpdatehelper.getstrftime())])
         return ['']


      if 'QUERY_STRING' in environ:
         querydict = cgi.parse_qs(environ['QUERY_STRING'], True, False)
      else:
         querydict = dict([])

      if 'listdir' in querydict:
         return self.processShowDirectory(mappedpath, displaypath, environ, start_response)      
      elif 'listtree' in querydict:
         return self.processShowTree(mappedpath, displaypath, environ, start_response)      
      else:
         return self.processPrettyShowDirectory(mappedpath, displaypath, normrelativepath, environ, start_response)


   def processTextPath(self, mappedpath, displaypath, recurs):
      proc_response = ''
      for f in os.listdir(mappedpath):
          fdisplaypath = self.cleanUpURLWithoutQuote(displaypath + URL_SEP + f)
          proc_response = proc_response + fdisplaypath + "\t"
      
          pathname = os.path.join(mappedpath, f)
          statresults = os.stat(pathname)
          mode = statresults[stat.ST_MODE]
   
          if stat.S_ISDIR(mode):
             proc_response = proc_response + "\tDirectory\t"
          elif stat.S_ISREG(mode):
             proc_response = proc_response + "\tFile\t" + str(statresults[stat.ST_SIZE])
          else:
             proc_response = proc_response + "\tUnknown\t" + str(statresults[stat.ST_SIZE])
   
          proc_response = proc_response + "\t" + str(statresults[stat.ST_MTIME]) + "\n"

          if stat.S_ISDIR(mode): 
             if recurs > 0:
                proc_response = proc_response + self.processTextPath(pathname, fdisplaypath, recurs - 1)  
             elif recurs == -1:
                proc_response = proc_response + self.processTextPath(pathname, fdisplaypath, recurs)  

      return proc_response                  

   def processShowTree(self, mappedpath, displaypath, environ, start_response):
      proc_response = displaypath + '\n' + self.processTextPath(mappedpath, displaypath, -1)
      start_response('200 OK', [('Content-Type', 'text/plain'), ('Date',httpdatehelper.getstrftime())])
      return [proc_response]
   
   def processShowDirectory(self, mappedpath, displaypath, environ, start_response):
      proc_response = displaypath + '\n' + self.processTextPath(mappedpath, displaypath, 0)
      start_response('200 OK', [('Content-Type', 'text/plain'), ('Date',httpdatehelper.getstrftime())])
      return [proc_response]

         
   def processPrettyShowDirectory(self, mappedpath, displaypath, normrelativepath, environ, start_response):
      proc_response = ''
      proc_response = proc_response + ('<html><head><title>PyFileServer - Index of ' + displaypath + '</title>')
      
      proc_response = proc_response + ('<style type="text/css">\nimg { border: 0; padding: 0 2px; vertical-align: text-bottom; }\ntd  { font-family: monospace; padding: 2px 3px; text-align: right; vertical-align: bottom; white-space: pre; }\ntd:first-child { text-align: left; padding: 2px 10px 2px 3px; }\ntable { border: 0; }\na.symlink { font-style: italic; }</style>')
      proc_response = proc_response + ('</head>\n')
      proc_response = proc_response + ('<body>')
      proc_response = proc_response + ('<H1>' + displaypath + '</H1>')
      proc_response = proc_response + ('<hr/><table>')
      
      if normrelativepath == '':
         proc_response = proc_response + ('<tr><td colspan="4">Top level share directory</td></tr>')
      else:
         proc_response = proc_response + ('<tr><td colspan="4"><a href="' + self.getLevelUpURL(displaypath) + '">Up to higher level directory</a></td></tr>')
    
      for f in os.listdir(mappedpath):
          proc_response = proc_response + '<tr>'
          proc_response = proc_response + '<td><A HREF="' + self.cleanUpURL(displaypath + URL_SEP + f) + '">'+ f + '</A></td>'
   
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
      proc_response = proc_response + self._infoHeader
      proc_response = proc_response + ('<BR>') + httpdatehelper.getstrftime()
      proc_response = proc_response + ('</body></html>\n')
      start_response('200 OK', [('Content-Type', 'text/html'), ('Date',httpdatehelper.getstrftime())])
      return [proc_response]


#For reference here:
#reByteRangeSpecifier = re.compile("(([0-9]+)\-([0-9]*))")
#reSuffixByteRangeSpecifier = re.compile("(\-([0-9]+))")

   def obtainContentRanges(self, rangetext, filesize):
      """
      returns tuple
      list: content ranges as values to their parsed components in the tuple (parsed component, seek_position/abs position of first byte, abs position of last byte, num_of_bytes_to_read)
      value: total length for Content-Length
      """
      listReturn = []
      totallength = 0
      seqRanges = rangetext.split(",")
      for subrange in seqRanges:
         matched = False
         if not matched:
            mObj = reByteRangeSpecifier.match(subrange)
            if mObj:
               firstpos = long(mObj.group(2))
               if mObj.group(3) == '':
                  lastpos = filesize - 1
               else:
                  lastpos = long(mObj.group(3))
               if firstpos <= lastpos and firstpos < filesize:
                  if lastpos >= filesize:
                     lastpos = filesize - 1
                  listReturn.append( (mObj.string[mObj.start(1):mObj.end(1)], firstpos , lastpos, lastpos - firstpos + 1) )
                  totallength = totallength + lastpos - firstpos + 1
                  matched = True
         if not matched:      
            mObj = reSuffixByteRangeSpecifier.match(subrange)
            if mObj:
               firstpos = filesize - long(mObj.group(2))
               if firstpos < 0:
                  firstpos = 0
               lastpos = filesize - 1
               listReturn.append( (mObj.string[mObj.start(1):mObj.end(1)], firstpos , lastpos, lastpos - firstpos + 1) )
               totallength = totallength + lastpos - firstpos + 1
               matched = True
      return (dictReturn, totallength)




   def doGETPOSTHEADFile(self, mappedpath, requestmethod, environ, start_response):
   
      if not os.path.isfile(mappedpath):
         raise ProcessRequestError(processrequesterrorhandler.HTTP_NOT_FOUND)
         
      statresults = os.stat(mappedpath)
      mode = statresults[stat.ST_MODE]
   
      filesize = statresults[stat.ST_SIZE]
      lastmodified = statresults[stat.ST_MTIME]
      entitytag = self._etagprovider(mappedpath, environ)

         
      ## Conditions

      # An HTTP/1.1 origin server, upon receiving a conditional request that includes both a Last-Modified date
      # (e.g., in an If-Modified-Since or If-Unmodified-Since header field) and one or more entity tags (e.g., 
      # in an If-Match, If-None-Match, or If-Range header field) as cache validators, MUST NOT return a response 
      # status of 304 (Not Modified) unless doing so is consistent with all of the conditional header fields in 
      # the request.

      if 'HTTP_IF_MATCH' in environ:
         ifmatchlist = environ['HTTP_IF_MATCH'].split(",")
         for ifmatchtag in ifmatchlist:
            ifmatchtag = ifmatchtag.strip(" \"\t")
            if ifmatchtag == entitytag or ifmatchtag == '*':
               break   
            raise ProcessRequestError(processrequesterrorhandler.HTTP_PRECONDITION_FAILED)
      
      # If-None-Match 
      # If none of the entity tags match, then the server MAY perform the requested method as if the 
      # If-None-Match header field did not exist, but MUST also ignore any If-Modified-Since header field
      # (s) in the request. That is, if no entity tags match, then the server MUST NOT return a 304 (Not Modified) 
      # response.
      ignoreifmodifiedsince = False         
      if 'HTTP_IF_NONE_MATCH' in environ:
         ifmatchlist = environ['HTTP_IF_NONE_MATCH'].split(",")
         for ifmatchtag in ifmatchlist:
            ifmatchtag = ifmatchtag.strip(" \"\t")
            if ifmatchtag == entitytag or ifmatchtag == '*':
               raise ProcessRequestError(processrequesterrorhandler.HTTP_PRECONDITION_FAILED)
         ignoreifmodifiedsince = True

      if 'HTTP_IF_UNMODIFIED_SINCE' in environ:
         ifunmodtime = httpdatehelper.getsecstime(environ['HTTP_IF_UNMODIFIED_SINCE'])
         if ifunmodtime:
            if ifunmodtime <= lastmodified:
               raise ProcessRequestError(processrequesterrorhandler.HTTP_PRECONDITION_FAILED)

      if 'HTTP_IF_MODIFIED_SINCE' in environ and not ignoreifmodifiedsince:
         ifmodtime = httpdatehelper.getsecstime(environ['HTTP_IF_MODIFIED_SINCE'])
         if ifmodtime:
            if ifmodtime > lastmodified:
               raise ProcessRequestError(processrequesterrorhandler.HTTP_NOT_MODIFIED)


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
         listRanges, totallength = self.obtainContentRanges(environ['HTTP_RANGE'], filesize)
         if len(listRanges) == 0:
            #No valid ranges present
            raise ProcessRequestError(processrequesterrorhandler.HTTP_RANGE_NOT_SATISFIABLE)

         #More than one range present -> take only the first range, since multiple range returns require multipart, which is not supported         
         #obtainContentRanges supports more than one range in case the above behaviour changes in future
         (rangedesc ,rangestart, rangeend, rangelength) = listRanges[0]
      else:
         (rangedesc ,rangestart, rangeend, rangelength) = ('default', 0L, filesize - 1, filesize)
         totallength = filesize

      ## Content Processing 

      (mimetype, mimeencoding) = mimetypes.guess_type(mappedpath); 
      if mimetype == '' or mimetype == None:
         mimetype = 'application/octet-stream' 
      
      fileistext = 0
      if mimetype.startswith("text"):
         fileistext = 1

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


      if requestmethod == 'HEAD':
         yield ''
         return

      if fileistext==0:
         fileobj = file(mappedpath, 'rb', BUFFER_SIZE)
      else:
         fileobj = file(mappedpath, 'r', BUFFER_SIZE)

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
   
   def getLevelUpURL(self, displayPath):
      listItems = displayPath.split(URL_SEP)
      listItems2 = []
      for item in listItems:
         if item!="":
            listItems2.append(item)
      listItems2.pop()
      return URL_SEP + urllib.quote(URL_SEP.join(listItems2))
      
   def cleanUpURL(self, displayURL):
      listItems = displayURL.split(URL_SEP)
      listItems2 = []
      for item in listItems:
         if item!="":
            listItems2.append(item)
      return URL_SEP + urllib.quote(URL_SEP.join(listItems2))

   def cleanUpURLWithoutQuote(self, displayURL):
      listItems = displayURL.split(URL_SEP)
      listItems2 = []
      for item in listItems:
         if item!="":
            listItems2.append(item)
      return URL_SEP + URL_SEP.join(listItems2) 
      
