import sys
import os
import os.path
import stat
import md5

"""
Sample ETag provider for PyFileServer

Non-file - md5(pathname)
Win32 - md5(pathname)-lastmodifiedtime-filesize
Others - inode-lastmodifiedtime-filesize
"""
      
def getETag(filePath, environ=None):
   if not os.path.isfile(filePath):
      return md5.new(filePath).hexdigest()   
   if sys.platform == 'win32':
      statresults = os.stat(filePath)
      return md5.new(filePath).hexdigest() + '-' + str(statresults[stat.ST_MTIME]) + '-' + str(statresults[stat.ST_SIZE])
   else:
      statresults = os.stat(filePath)
      return str(statresults[stat.ST_INO]) + '-' + str(statresults[stat.ST_MTIME]) + '-' + str(statresults[stat.ST_SIZE])

   