import os
import shelve
import threading

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
      if normurl not in self._dict:
         return []
      else:
         return self._dict[normurl].keys()

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
      if normurl not in self._dict:
         locatordict = self._dict[normurl] 
      else:
         locatordict = dict([])    
      locatordict[propertyname] = propertyvalue
      self._dict[normurl] = locatordict
      self._dict.sync()

   
   def __del__(self):
      if self._loaded:
         self._dict.close()










