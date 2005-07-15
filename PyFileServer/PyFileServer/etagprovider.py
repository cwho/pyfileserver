import sys
import os
import stat
import md5

"""
Sample ETag provider for PyFileServer

Win32 - 'md5' + md5(pathname)-lastmodifiedtime-filesize
Others - inode-lastmodifiedtime-filesize
"""
      
def getETag(filePath, environ=None):
   if sys.platform == 'win32':
      pathmd5 = md5.new()
      pathmd5.update(filePath)
      md5digest = pathmd5.digest()
      
      statresults = os.stat(filePath)
      return 'md5' + md5digest + '-' + str(statresults[stat.ST_MTIME]) + '-' + str(statresults[stat.ST_SIZE])
   else:
      statresults = os.stat(filePath)
      return str(statresults[stat.ST_INO]) + '-' + str(statresults[stat.ST_MTIME]) + '-' + str(statresults[stat.ST_SIZE])

   