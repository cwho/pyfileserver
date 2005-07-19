import os
import os.path
import sys
import mimetypes
import stat
import websupportfuncs
import httpdatehelper
import etagprovider

from xml.dom.ext.reader import Sax2
import xml.dom.ext
from xml.dom import implementation, Node

import processrequesterrorhandler
from processrequesterrorhandler import ProcessRequestError

class WebDAVImplementation(object):
   def __init__(self, propertymanager, etagproviderfunc = etagprovider.getETag):
      self._propertymanager = propertymanager
      self._etagprovider = etagproviderfunc
      
   def doPROPFIND(self, mappedpath, displaypath, environ, start_response):
      if 'wsgi.input' not in environ:
         raise ProcessRequestError(processrequesterrorhandler.HTTP_BAD_REQUEST)
      inputstream = environ['wsgi.input']
      
      doc = Sax2.Reader().fromStream(inputstream)
      

      pfroot = doc.documentElement
      if pfroot.namespaceURI != 'DAV:' or pfroot.localName != 'propfind':
         raise ProcessRequestError(404)   
      
      propList = []
      propFindMode = 3
      pfnodeList = pfroot.childNodes
      for pfnode in pfnodeList:
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
                  propList.append( (pfpnode.namespaceURI, pfpnode.localName) )       

      if 'HTTP_DEPTH' not in environ:
         environ['HTTP_DEPTH'] = '0'
      
      reslist = websupportfuncs.getDepthActionList(mappedpath, displaypath, environ['HTTP_DEPTH'], True)

      yield "<?xml version='1.0' encoding='UTF-8'?>"
      yield "<multistatus xmlns='DAV:'>"
      for (respath , resdisplayname) in reslist:
         yield "<response>"
         yield "<href>" + resdisplayname + "</href>"    

         if propFindMode == 1 or propFindMode == 2:
            propList = self.getApplicablePropertyNames(respath, resdisplayname)
            
         if propFindMode == 2:
            yield "<propstat>"
            yield "<prop>"
            for (propns, propname) in propList:
               if propns == 'DAV:':
                  yield "<" + propname + "/>"
               else:
                  yield "<" + propname + " xmlns='" + propns + "'/>"
            yield "</prop>"
            yield "<status>HTTP/1.1 200 OK</status>"
            yield "</propstat>"
         else:
            for (propns, propname) in propList:
               propvalue, propstatus = self.getProperty(respath, resdisplayname, propns, propname)
               
               yield "<propstat>" 
               yield "<prop>"
               
               if propns == 'DAV:':
                  yield "<" + propname + ">"
               else:
                  yield "<" + propname + " xmlns='" + propns + "' >"
               if propvalue != None:
                  yield propvalue
               yield "</"+propname+">" 
               yield "</prop>"              
               yield "<status>HTTP/1.1 " + propstatus + "</status>"
               yield "</propstat>"
         yield "</response>"
      yield "</multistatus>"      
      return 


   def getProperty(self, mappedpath, displaypath, propns, propname):
      if propns == 'DAV:':
         isfile = os.path.isfile(mappedpath)
         if propname == 'creationdate':
            statresults = os.stat(mappedpath)
            return (httpdatehelper.getstrftime(statresults[stat.ST_CTIME]), "200 OK")        
         elif propname == 'displayname':
            return (displaypath, "200 OK")
         elif propname == 'getcontenttype':
            if isfile:
               (mimetype, mimeencoding) = mimetypes.guess_type(mappedpath);
               if mimetype == '' or mimetype == None:
                   mimetype = 'application/octet-stream'             
               return (mimetype, "200 OK")
            else:
               return ('text/html', "200 OK")
         elif propname == 'resourcetype':
            return ('', "200 OK")   
         elif propname == 'getlastmodified':
            statresults = os.stat(mappedpath)
            return (httpdatehelper.getstrftime(statresults[stat.ST_MTIME]), "200 OK")                     
         elif propname == 'getcontentlength':
            if isfile:
               statresults = os.stat(mappedpath)
               return (str(statresults[stat.ST_SIZE]), "200 OK")
            return (None, "404 Not Found")
         elif propname == 'getetag':
            if isfile:
               return (self._etagprovider(mappedpath), "200 OK")
            return (None, "404 Not Found")
         elif propname == 'getcontentlanguage' or propname == 'source' or propname == 'lockdiscovery' or propname == 'supportedlock':
            return (None, "404 Not Found")
         
      propvalue = self._propertymanager.getProperty(displaypath, propns + ';' + propname)
      if propvalue == None:
         return (None, "404 Not Found")
      else:
         return (propvalue, "200 OK")


   
   def getApplicablePropertyNames(self, mappedpath, displaypath):
      appProps = []
      #DAV properties for all resources
      appProps.append( ('DAV:','creationdate') )
      appProps.append( ('DAV:','displayname') )
      appProps.append( ('DAV:','getcontenttype') )
      appProps.append( ('DAV:','resourcetype') )
      appProps.append( ('DAV:','getlastmodified') )   
      
      #appProps.append( ('DAV:','getcontentlanguage') ) # not supported
      #appProps.append( ('DAV:','source') ) # not supported
      
      #appProps.append( ('DAV:','lockdiscovery') ) # not supported yet
      #appProps.append( ('DAV:','supportedlock') ) # not supported yet
      
      if os.path.isfile(mappedpath):
         appProps.append( ('DAV:','getcontentlength') )
         appProps.append( ('DAV:','getetag') )
      
      otherprops = self._propertymanager.getProperties(displaypath)
      for otherprop in otherprops:
         otherns, othername = otherprop.split(':',1)
         appProps.append(otherns, othername)
      return appProps