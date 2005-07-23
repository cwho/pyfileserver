import os
import os.path
import shelve
import threading
import stat
import mimetypes
import httpdatehelper

"""
A low performance dead properties library using shelve

TODO possibilities:
+ some other persistent library
+ separate shelf for each realm for better management and realm portability
"""

class PropertyManager(object):

   def __init__(self, persiststore):
      self._loaded = False      
      self._dict = None
      self._lock = threading.Lock()
      self._persiststorepath = persiststore
   

   def performInitialization(self):
      self._lock.acquire(True)
      if self._loaded:       # test again within the critical section
         self._lock.release()
         return True
      self._dict = shelve.open(self._persiststorepath)
      self._lock.release()         

   def getProperties(self, normurl):
      if not self._loaded:
         self.performInitialization()
      if normurl in self._dict:
         return self._dict[normurl].keys()
      else:
         return []

   def getProperty(self, normurl, propertyname):
      if not self._loaded:
         self.performInitialization()
      if normurl not in self._dict:
         return None
      resourceprops = self._dict[normurl]
      if propertyname not in resourceprops:
         return None
      else:
         return resourceprops[propertyname]
      
   def writeProperty(self, normurl, propertyname, propertyvalue):
      if not self._loaded:
         self.performInitialization()
      if normurl in self._dict:
         locatordict = self._dict[normurl] 
      else:
         locatordict = dict([])    
      locatordict[propertyname] = propertyvalue
      self._dict[normurl] = locatordict
      self._dict.sync()

   def removeProperty(self, normurl, propertyname):
      if not self._loaded:
         self.performInitialization()
      if normurl in self._dict:      
         locatordict = self._dict[normurl] 
      else:
         return
      if propertyname in locatordict:
         del locatordict[propertyname]
      else:
         return            
      self._dict[normurl] = locatordict
      self._dict.sync()
   
   def removeProperties(self, normurl):
      if not self._loaded:
         self.performInitialization()
      if normurl in self._dict:      
         del self._dict[normurl] 
      return
   
   def copyProperties(self, origurl, desturl):
      if not self._loaded:
         self.performInitialization()
      if origurl in self._dict:      
         self._dict[desturl] = self._dict[origurl].copy() 
      return
   
   def getString(self):
      return str(self._dict)
   
   def __del__(self):
      if self._loaded:
         self._dict.close()




def writeProperty(pm, mappedpath, displaypath, propns, propname, propupdatemethod, propvalue, reallydoit = True):
   reservedprops = ['creationdate', 'displayname', 'getcontenttype','resourcetype','getlastmodified', 'getcontentlength', 'getetag', 'getcontentlanguage', 'source', 'lockdiscovery', 'supportedlock']
   if propns == None:
      propns = ''
   
   if propns == 'DAV:':
      if propname in reservedprops:
         return "409 Conflict"
   
   if reallydoit:
      if propupdatemethod == 'set':
         pm.writeProperty(displaypath, propns + ';' + propname, propvalue)
      elif propupdatemethod == 'remove':
         pm.removeProperty(displaypath, propns + ';' + propname)
   return "200 OK"      
   
def getProperty(pm, mappedpath, displaypath, propns, propname, etagprovider):
   if propns == None:
      propns = ''

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
         if os.path.isdir(mappedpath):
            return ('<collection />', "200 OK")            
         else:
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
            return (etagprovider(mappedpath), "200 OK")
         return (None, "404 Not Found")
      elif propname == 'getcontentlanguage' or propname == 'source' or propname == 'lockdiscovery' or propname == 'supportedlock':
         return (None, "404 Not Found")
      
   propvalue = pm.getProperty(displaypath, propns + ';' + propname)
   if propvalue == None:
      return (None, "404 Not Found")
   else:
      return (propvalue, "200 OK")



def getApplicablePropertyNames(pm, mappedpath, displaypath):
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
   
   otherprops = pm.getProperties(displaypath)
   for otherprop in otherprops:
      otherns, othername = otherprop.split(';',1)
      appProps.append( (otherns, othername) )
   return appProps







