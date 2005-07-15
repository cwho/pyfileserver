import calendar
import time
import os

"""
HTTP dates helper
"""

def getstrftime(secs=None):
   """
   rfc 1123 date/time format
   """
   return time.strftime('%a, %d %b %Y %H:%M:%S GMT', time.gmtime(secs))


def getsecstime(timeformat):
   """
   attempts to get gmtime tuple from timeformat, returns None if unsuccessful   
   """
   result = getgmtime(timeformat)
   if result:
      return calendar.timegm(result)
   else:
      return None

def getgmtime(timeformat):
   """
   attempts to get gmtime tuple from timeformat, returns None if unsuccessful
   """

   # Sun, 06 Nov 1994 08:49:37 GMT  ; RFC 822, updated by RFC 1123
   try:
      vtime = time.strptime(timeformat, "%a, %d %b %Y %H:%M:%S GMT")   
      return vtime
   except:
      pass

   # Sunday, 06-Nov-94 08:49:37 GMT ; RFC 850, obsoleted by RFC 1036
   try:
      vtime = time.strptime(timeformat, "%A %d-%b-%y %H:%M:%S GMT")
      return vtime
   except:
      pass   

   # Sun Nov  6 08:49:37 1994       ; ANSI C's asctime() format  
   try:
      vtime = time.strptime(timeformat, "%a %b %d %H:%M:%S %Y")
      return vtime
   
   except:
      pass
      
   return None



