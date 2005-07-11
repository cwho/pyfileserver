import os
import os.path
import sys
import stat
import urllib
import time
import mimetypes
import cgi

from paste import wsgilib

import MappingConfiguration
from ProcessRequestErrorHandler import ProcessRequestError
import ProcessRequestErrorHandler

# CONSTANTS
URL_SEP = '/'

class RequestServer(object):
   def __init__(self, srvconfig, infoHeader = None):
      self._srvcfg = srvconfig
      self._infoHeader = infoHeader
      
   def __call__(self, environ, start_response):
      mapcfg = self._srvcfg['config_mapping']
      mapcfgkeys = mapcfg.keys()
      mapcfgkeys.sort()
      mapcfgkeys.reverse()
   
      requestpath =  urllib.unquote(environ['PATH_INFO'])
         
      mapdirprefix = ''
      mapdirprefixfound = 0
      for tmp_mapdirprefix in mapcfgkeys:
         if self._srvcfg['MapKeysCaseSensitive'] == 1: 
            if requestpath == tmp_mapdirprefix or requestpath.startswith(tmp_mapdirprefix + URL_SEP):
               mapdirprefixfound = 1
               mapdirprefix = tmp_mapdirprefix   
               break         
         else:
            if requestpath.upper() == tmp_mapdirprefix.upper() or requestpath.upper().startswith(tmp_mapdirprefix.upper() + URL_SEP):
               mapdirprefixfound = 1
               mapdirprefix = tmp_mapdirprefix   
               break         
   
      if mapdirprefixfound == 0:
         raise ProcessRequestError(ProcessRequestErrorHandler.HTTP_NOT_FOUND)
            
      relativepath = requestpath[len(mapdirprefix):]
      relativepath = relativepath.replace(URL_SEP, os.sep)
   
      if relativepath.endswith(os.sep):
         relativepath = relativepath[:-len(os.sep)] # remove suffix os.sep since it causes error (SyntaxError) with os.path functions
   
      normrelativepath = ''
      if relativepath != '':          # avoid adding of .s
         normrelativepath = os.path.normpath(relativepath)   
         
      # Note: Firefox apparently resolves .. and . on client side before sending it to server. IE doesnt.
        
      if self._srvcfg['AllowRelativePaths'] == 0:
         if normrelativepath != relativepath:
            raise ProcessRequestError(ProcessRequestErrorHandler.HTTP_FORBIDDEN)
      
      mappedpath = mapcfg[mapdirprefix] + os.sep + normrelativepath
      requestmethod =  environ['REQUEST_METHOD'].upper()
      
      if(normrelativepath != ""):
         displaypath = mapdirprefix + normrelativepath.replace(os.sep, URL_SEP)
      else:
         displaypath = mapdirprefix + URL_SEP
      
      proc_response = ''
      if (requestmethod == 'GET' or requestmethod == 'POST') and os.path.isdir(mappedpath): 
         return self.doGETPOSTDirectory(mappedpath, displaypath, normrelativepath, environ, start_response)
      elif (requestmethod == 'GET' or requestmethod == 'POST') and os.path.isfile(mappedpath):
         return self.doGETPOSTFile(mappedpath, environ, start_response)
      #elif requestmethod == 'PUT':
      #   return processGetFile(mappedpath, environ, start_response)
      else:
         raise self.ProcessRequestError(ProcessRequestErrorHandler.HTTP_NOT_FOUND)


   def doGETPOSTDirectory(self, mappedpath, displaypath, normrelativepath, environ, start_response):
      if not os.path.isdir(mappedpath):
         raise ProcessRequestError(ProcessRequestErrorHandler.HTTP_NOT_FOUND)

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
   
          proc_response = proc_response + "\t" + repr(statresults[stat.ST_MTIME]) + "\n"

          if stat.S_ISDIR(mode): 
             if recurs > 0:
                proc_response = proc_response + self.processTextPath(pathname, fdisplaypath, recurs - 1)  
             elif recurs == -1:
                proc_response = proc_response + self.processTextPath(pathname, fdisplaypath, recurs)  

      return proc_response                  

   def processShowTree(self, mappedpath, displaypath, environ, start_response):
      proc_response = displaypath + '\n' + self.processTextPath(mappedpath, displaypath, -1)
      start_response('200 OK', [('Content-type', 'text/plain')])
      return [proc_response]
   
   def processShowDirectory(self, mappedpath, displaypath, environ, start_response):
      proc_response = displaypath + '\n' + self.processTextPath(mappedpath, displaypath, 0)
      start_response('200 OK', [('Content-type', 'text/plain')])
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
   
          proc_response = proc_response + '<td>' + time.asctime(time.gmtime(statresults[stat.ST_MTIME])) + ' GMT</td>'
          proc_response = proc_response + '</tr>\n'
   
      proc_response = proc_response + ('</table><hr>')
      proc_response = proc_response + self._infoHeader
      proc_response = proc_response + ('<BR>') + time.asctime(time.gmtime(statresults[stat.ST_MTIME])) + (' GMT')
      proc_response = proc_response + ('</body></html>\n')
      start_response('200 OK', [('Content-type', 'text/html')])
      return [proc_response]


   def doGETPOSTFile(self, mappedpath, environ, start_response):
   
      if not os.path.isfile(mappedpath):
         raise ProcessRequestError(ProcessRequestErrorHandler.HTTP_NOT_FOUND)
         
      statresults = os.stat(mappedpath)
      mode = statresults[stat.ST_MODE]
   
      filesize = str(statresults[stat.ST_SIZE])
      lastmodified = time.asctime(time.gmtime(statresults[stat.ST_MTIME])) + " GMT"
      BUFFER_SIZE = 8192
   
      (mimetype, mimeencoding) = mimetypes.guess_type(mappedpath); 
      if mimetype == '' or mimetype == None:
         mimetype = 'application/octet-stream' 
      
      fileistext = 0
      if mimetype.startswith("text"):
         fileistext = 1
      
      if fileistext==0:
         fileobj = file(mappedpath, 'rb', BUFFER_SIZE)
      else:
         fileobj = file(mappedpath, 'r', BUFFER_SIZE)
   
      responseHeaders = []
      responseHeaders.append(('Content-type', mimetype))
      responseHeaders.append(('Content-Length', filesize))
      responseHeaders.append(('Last-Modified', lastmodified))
   
   #   start_response('200 OK', [('Content-type', mimetype), ('Content-type', mimetype)] )
      start_response('200 OK', responseHeaders)
   
      readbuffer = 'start'
      while len(readbuffer) != 0:
         readbuffer = fileobj.read(BUFFER_SIZE)
         yield readbuffer
   
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