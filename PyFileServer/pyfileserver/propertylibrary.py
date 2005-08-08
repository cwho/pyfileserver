"""
propertylibrary
===============

:Module: pyfileserver.propertylibrary
:Author: Ho Chun Wei, fuzzybr80(at)gmail.com
:Project: PyFileServer, http://pyfilesync.berlios.de/
:Copyright: Lesser GNU Public License, see LICENSE file attached with package

This module consists of a number of miscellaneous functions for the locks and 
properties features of webDAV.

It also includes an implementation of a LockManager and a PropertyManager for
storage of locks and dead properties respectively. These implementations use
shelve for file storage.

*author note*: More documentation here required

See extrequestserver.py for details::

   class LockManager   
      __init__(self, persiststore)
      __repr__(self)
      __del__(self)
      performInitialization(self)
      generateLock(self, username, locktype = 'write', lockscope = 'exclusive', lockdepth = 'infinite', lockowner = '', timeout=LOCK_TIME_OUT_DEFAULT)
      validateLock(self, locktoken)
      deleteLock(self, locktoken)
      isTokenLockedByUser(self, locktoken, username)
      isURLLocked(self, url)
      getLockProperty(self, locktoken, lockproperty)
      isURLLockedByToken(self, url, locktoken)
      getURLLocktokenList(self, url)
      getURLLocktokenListOfUser(self, url, username)
      addURLToLock(self, url, locktoken)
      removeAllLocksFromURL(self, url)
      refreshLock(self, locktoken, timeout=LOCK_TIME_OUT_DEFAULT)
      checkLocksToAdd(self, displaypath)
   
   class PropertyManager
      __init__(self, persiststore)
      __repr__(self)
      __del__(self)
      performInitialization(self)
      getProperties(self, normurl)
      getProperty(self, normurl, propertyname)
      writeProperty(self, normurl, propertyname, propertyvalue)
      removeProperty(self, normurl, propertyname)
      removeProperties(self, normurl)
      copyProperties(self, origurl, desturl)
   
   
   Note: Custom implementations of LockManager and PropertyManager do *not* have
   to implement the following miscellaneous functions   
   
   Miscellaneous functions
      readTimeoutValueHeader(timeoutvalue)
      writeProperty(pm, mappedpath, displaypath, propns, propname, propupdatemethod, propvalue, reallydoit=True)
      getProperty(pm, lm, mappedpath, displaypath, propns, propname, etagprovider)
      getApplicablePropertyNames(pm, mappedpath, displaypath)
   

This module is specific to the PyFileServer application.

"""

__docformat__ = 'reStructuredText'

import os
import os.path
import shelve
import threading
import stat
import mimetypes
import random
import re
import time

import httpdatehelper
import websupportfuncs

"""
A low performance lock library using shelve

TODO possibilities:
+ some other persistent library
+ separate shelf for each realm for better management and realm portability
+ better resolution locks for higher performance
"""

LOCK_TIME_OUT_DEFAULT = 604800 # 1 week, in seconds

class LockManager(object):
   def __init__(self, persiststore):
      self._loaded = False      
      self._dict = None
      self._init_lock = threading.RLock()
      self._write_lock = threading.RLock()
      self._persiststorepath = persiststore

   def performInitialization(self):
      self._init_lock.acquire(True)
      try:
         if self._loaded:       # test again within the critical section
            self._lock.release()
            return True
         self._dict = shelve.open(self._persiststorepath)
      finally:
         self._init_lock.release()         

   def __repr__(self):
      return repr(self._dict)
   
   def __del__(self):
      if self._loaded:
         self._dict.close()   

   def generateLock(self, username, locktype = 'write', lockscope = 'exclusive', lockdepth = 'infinite', lockowner = '', lockheadurl = '', timeout = LOCK_TIME_OUT_DEFAULT):
      self._write_lock.acquire(True)
      try:
         if not self._loaded:
            self.performInitialization()
         randtoken = "opaquelocktoken:" + str(hex(random.getrandbits(256)))
         while ('LOCKTIME:'+ randtoken) in self._dict:
            randtoken = "opaquelocktoken:" + str(hex(random.getrandbits(256)))
         if timeout < 0:
            self._dict['LOCKTIME:'+ randtoken] = -1      
         else:
            self._dict['LOCKTIME:'+ randtoken] = time.time() + timeout
         self._dict['LOCKUSER:'+ randtoken] = username
         self._dict['LOCKTYPE:'+ randtoken] = locktype
         self._dict['LOCKSCOPE:'+ randtoken] = lockscope
         self._dict['LOCKDEPTH:'+ randtoken] = lockdepth
         self._dict['LOCKOWNER:'+randtoken] = lockowner
         self._dict['LOCKHEADURL:'+randtoken] = lockheadurl
         return randtoken
      finally:
         self._dict.sync()
         self._write_lock.release()

   def validateLock(self, locktoken):
      if not self._loaded:
         self.performInitialization()
      if ('LOCKTIME:'+ locktoken) in self._dict:
         if self._dict['LOCKTIME:'+ locktoken] > 0 and self._dict['LOCKTIME:'+ locktoken] < time.time():
            self.deleteLock(locktoken)   
            return False
      else:
         self.deleteLock(locktoken)      
         return False
      return True

   def deleteLock(self, locktoken):
      self._write_lock.acquire(True)      
      try:
         if not self._loaded:
            self.performInitialization()
         if ('LOCKTIME:'+ locktoken) in self._dict:
            del self._dict['LOCKTIME:'+ locktoken]       
         if ('LOCKUSER:'+ locktoken) in self._dict:
            del self._dict['LOCKUSER:'+ locktoken]       
         if ('LOCKTYPE:'+ locktoken) in self._dict:
            del self._dict['LOCKTYPE:'+ locktoken]
         if ('LOCKSCOPE:'+ locktoken) in self._dict:
            del self._dict['LOCKSCOPE:'+ locktoken]
         if ('LOCKDEPTH:'+ locktoken) in self._dict:
            del self._dict['LOCKDEPTH:'+ locktoken]
         if ('LOCKOWNER:'+ locktoken) in self._dict:
            del self._dict['LOCKOWNER:'+ locktoken]
         if ('LOCKHEADURL:'+ locktoken) in self._dict:
            del self._dict['LOCKHEADURL:'+ locktoken]
         if ('LOCKURLS:'+locktoken) in self._dict:       
            for urllocked in self._dict['LOCKURLS:'+locktoken]:
               if ('URLLOCK:' + urllocked) in self._dict:
                  urllockdict = self._dict['URLLOCK:' + urllocked]
                  if locktoken in urllockdict:
                     del urllockdict[locktoken]
                  if len(urllockdict) == 0:
                     del self._dict['URLLOCK:' + urllocked]
                  else:
                     self._dict['URLLOCK:' + urllocked] = urllockdict 
            del self._dict['LOCKURLS:'+locktoken]  
      finally:
         self._dict.sync()
         self._write_lock.release()

   def isTokenLockedByUser(self, locktoken, username):
      if not self._loaded:
         self.performInitialization()
      if self.validateLock(locktoken):
         return ('LOCKUSER:'+locktoken) in self._dict      
      else:
         return False
   
   def isURLLocked(self, url):
      if not self._loaded:
         self.performInitialization()
      if ('URLLOCK:' + url) in self._dict:
         urllockdictcopy = self._dict['URLLOCK:' + url].copy()  # use read-only copy here, since validation can delete the dictionary
         for urllocktoken in urllockdictcopy:
            if self.validateLock(urllocktoken):
               if ('LOCKSCOPE:'+ urllocktoken) in self._dict: # either one exclusive lock, or many shared locks - first lock will give lock scope
                  return self._dict['LOCKSCOPE:'+ urllocktoken]
               return "unknown" # not usually reached
         return None
      else:
         return None
   
   # lockproperty one of 'LOCKSCOPE', 'LOCKUSER', 'LOCKTYPE', 'LOCKDEPTH', 'LOCKTIME', 'LOCKOWNER' note case
   def getLockProperty(self, locktoken, lockproperty):
      if (lockproperty + ":" + locktoken) in self._dict: 
         lockpropvalue = self._dict[lockproperty + ":" + locktoken]         
         if lockproperty == 'LOCKTIME':
            if lockpropvalue < 0:
               return 'Infinite'
            else:
               return 'Second-' + str(long(lockpropvalue - time.time())) 
         return lockpropvalue
      else:
         return ''
         
   def isURLLockedByToken(self, url, locktoken):   
      if not self._loaded:
         self.performInitialization()
      if ('URLLOCK:' + url) in self._dict:
         urllockdictcopy = self._dict['URLLOCK:' + url].copy()  # use read-only copy here, since validation can delete the dictionary
         for urllocktoken in urllockdictcopy:
            if self.validateLock(urllocktoken) and urllocktoken == locktoken:
               return True
         return False
      else:
         return False
   
   def getURLLocktokenList(self, url):
      listReturn = []
      if not self._loaded:
         self.performInitialization()
      if ('URLLOCK:' + url) in self._dict:
         urllockdictcopy = self._dict['URLLOCK:' + url].copy()  # use read-only copy here, since validation can delete the dictionary
         for urllocktoken in urllockdictcopy:
            if self.validateLock(urllocktoken):
               listReturn.append(urllocktoken)
      return listReturn

   def getURLLocktokenListOfUser(self, url, username):
      listReturn = []
      if not self._loaded:
         self.performInitialization()
      if ('URLLOCK:' + url) in self._dict:
         urllockdictcopy = self._dict['URLLOCK:' + url].copy()  # use read-only copy here, since validation can delete the dictionary
         for urllocktoken in urllockdictcopy:
            if self.isTokenLockedByUser(urllocktoken, username):
               listReturn.append(urllocktoken)
      return listReturn

      
   def addURLToLock(self, url, locktoken):
      self._write_lock.acquire(True)
      try:
         if not self._loaded:
            self.performInitialization()
         if self.validateLock(locktoken):            
            if ('URLLOCK:' + url) in self._dict:
               urllockdict = self._dict['URLLOCK:' + url]      
               urllockdict[locktoken] = locktoken
               self._dict['URLLOCK:' + url] = urllockdict
            else:
               self._dict['URLLOCK:' + url] = dict([(locktoken ,locktoken )])

            if ('LOCKURLS:'+locktoken) in self._dict:  
               urllockdict = self._dict['LOCKURLS:'+locktoken]
               urllockdict[url] = url
               self._dict['LOCKURLS:'+locktoken] = urllockdict
            else:
               self._dict['LOCKURLS:'+locktoken] = dict([(url, url)])
            return True
         else:
            return False
      finally:
         self._dict.sync()
         self._write_lock.release()               
      
   def removeAllLocksFromURL(self, url):
      self._write_lock.acquire(True)
      try:
         if not self._loaded:
            self.performInitialization()
         if ('URLLOCK:' + url) in self._dict:
            urllockdictcopy = self._dict['URLLOCK:' + url].copy()  # use read-only copy here, since validation can delete the dictionary
            for urllocktoken in urllockdictcopy:
               if self.validateLock(urllocktoken):
                  if ('LOCKURLS:'+locktoken) in self._dict:       
                     urllockdict = self._dict['LOCKURLS:'+locktoken]
                     if url in urllockdict:
                        del urllockdict[url]
                        if len(urllockdict) == 0:
                           self.deleteLock(locktoken)
                        else:                
                           self._dict['LOCKURLS:'+locktoken] = urllockdict
            if ('URLLOCK:' + url) in self._dict:  # check again, deleteLock might have removed it
               del self._dict['URLLOCK:' + url]      
      finally:
         self._dict.sync()
         self._write_lock.release()               
      
   def refreshLock(self, locktoken, timeout = LOCK_TIME_OUT_DEFAULT):
      self._write_lock.acquire(True)
      try:
         if not self._loaded:
            self.performInitialization()
         if ('LOCK:'+ locktoken) in self._dict:
            self._dict['LOCK:'+ locktoken] = time.time() + timeout
            return True
         return False
      finally:
         self._dict.sync()
         self._write_lock.release()

   def checkLocksToAdd(self, displaypath):
      if not self._loaded:
         self.performInitialization()
      parentdisplaypath = websupportfuncs.getLevelUpURL(displaypath)
      if self.isURLLocked(parentdisplaypath) != None:
         locklist = self.getURLLocktokenList(parentdisplaypath)
         for locklisttoken in locklist:
            if self.getLockProperty(locklisttoken, 'LOCKDEPTH') == 'infinity':
               if not self.isURLLockedByToken(displaypath, locklisttoken):
                  self.addURLToLock(displaypath, locklisttoken)

# returns -1 if infinite, else return numofsecs
# any numofsecs above the following limit is regarded as infinite
MAX_FINITE_TIMEOUT_LIMIT = 10*365*24*60*60  #approx 10 years
#LOCK_TIME_OUT_DEFAULT = 604800 # 1 week, in seconds (copied from above)

reSecondsReader = re.compile("[Ss][Ee][Cc][Oo][Nn][Dd]\\-([0-9]+)")

def readTimeoutValueHeader(timeoutvalue):
   timeoutsecs = 0
   timeoutvaluelist = timeoutvalue.split(',')   
   for timeoutspec in timeoutvaluelist:
      timeoutspec = timeoutspec.strip()
      if timeoutspec.lower() == 'infinite':
         return -1
      else:
         listSR = reSecondsReader.findall(timeoutspec)
         for secs in listSR:
            timeoutsecs = long(secs)
            if timeoutsecs > MAX_FINITE_TIMEOUT_LIMIT:
               return -1          
            if timeoutsecs != 0:
               return timeoutsecs
   return LOCK_TIME_OUT_DEFAULT
   

   
"""
A low performance dead properties library using shelve

TODO possibilities:
+ some other persistent library
+ separate shelf for each realm for better management and realm portability
+ better resolution locks for higher performance
"""

class PropertyManager(object):

   def __init__(self, persiststore):
      self._loaded = False      
      self._dict = None
      self._init_lock = threading.RLock()
      self._write_lock = threading.RLock()
      self._persiststorepath = persiststore
   

   def performInitialization(self):
      self._init_lock.acquire(True)
      try:
         if self._loaded:       # test again within the critical section
            self._lock.release()
            return True
         self._dict = shelve.open(self._persiststorepath)
      finally:
         self._init_lock.release()         

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
      self._write_lock.acquire(True)
      try:
         if not self._loaded:
            self.performInitialization()
         if normurl in self._dict:
            locatordict = self._dict[normurl] 
         else:
            locatordict = dict([])    
         locatordict[propertyname] = propertyvalue
         self._dict[normurl] = locatordict
         self._dict.sync()
      finally:
         self._write_lock.release()         

   def removeProperty(self, normurl, propertyname):
      self._write_lock.acquire(True)
      try:
         if not self._loaded:
            self.performInitialization()
         if normurl in self._dict:      
            locatordict = self._dict[normurl] 
            if propertyname in locatordict:
               del locatordict[propertyname]
               self._dict[normurl] = locatordict
               self._dict.sync()
      finally:
         self._write_lock.release()         
   
   def removeProperties(self, normurl):
      self._write_lock.acquire(True)
      try:
         if not self._loaded:
            self.performInitialization()
         if normurl in self._dict:      
            del self._dict[normurl] 
      finally:
         self._write_lock.release()         
   
   def copyProperties(self, origurl, desturl):
      self._write_lock.acquire(True)
      try:
         if not self._loaded:
            self.performInitialization()
         if origurl in self._dict:      
            self._dict[desturl] = self._dict[origurl].copy() 
      finally:
         self._write_lock.release()         
   
   def __repr__(self):
      return repr(self._dict)
   
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
   
def getProperty(pm, lm, mappedpath, displaypath, propns, propname, etagprovider):
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
            return ('<D:collection />', "200 OK")            
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
      elif propname == 'lockdiscovery':
         lockinfo = ''         
         activelocklist = lm.getURLLocktokenList(displaypath)
         for activelocktoken in activelocklist:
            lockinfo = lockinfo + '<D:activelock>\n'
            lockinfo = lockinfo + '<D:locktype><' + lm.getLockProperty(activelocktoken, 'LOCKTYPE') + '/></D:locktype>\n'
            lockinfo = lockinfo + '<D:lockscope><' + lm.getLockProperty(activelocktoken, 'LOCKSCOPE') + '/></D:lockscope>\n'
            lockinfo = lockinfo + '<D:depth>' + lm.getLockProperty(activelocktoken, 'LOCKDEPTH') + '</D:depth>\n'
            lockinfo = lockinfo + '<D:owner>' + lm.getLockProperty(activelocktoken, 'LOCKOWNER') + '</D:owner>\n'
            lockinfo = lockinfo + '<D:timeout>' + lm.getLockProperty(activelocktoken, 'LOCKTIME') + '</D:timeout>\n'
            lockinfo = lockinfo + '<D:locktoken><D:href>' + activelocktoken + '</D:href></D:locktoken>\n'
            lockinfo = lockinfo + '</D:activelock>\n'
         return (lockinfo, "200 OK")
      elif propname == 'supportedlock':
         return ('<D:lockentry xmlns:D=\"DAV:\" >\n<D:lockscope><D:exclusive/></D:lockscope>\n<D:locktype><D:write/></D:locktype>\n</D:lockentry>\n<D:lockentry xmlns:D=\"DAV:\" >\n<D:lockscope><D:shared/></D:lockscope>\n<D:locktype><D:write/></D:locktype>\n</D:lockentry>', "200 OK")
      elif propname == 'getcontentlanguage' or propname == 'source':
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
   appProps.append( ('DAV:','lockdiscovery') ) 
   appProps.append( ('DAV:','supportedlock') ) 
   
   if os.path.isfile(mappedpath):
      appProps.append( ('DAV:','getcontentlength') )
      appProps.append( ('DAV:','getetag') )
   
   otherprops = pm.getProperties(displaypath)
   for otherprop in otherprops:
      otherns, othername = otherprop.split(';',1)
      appProps.append( (otherns, othername) )
   return appProps







