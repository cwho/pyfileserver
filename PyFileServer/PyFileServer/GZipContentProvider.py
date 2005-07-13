## THIS MODULE IS WORK IN PROGRESS

import gzip
import StringIO

fileobj = open('c:\\ReadmeFirst.htm', 'r')

zipbuffer = StringIO.StringIO()
zipfinal = ''
gzipfile = gzip.GzipFile(fileobj=zipbuffer,mode='wb')

readbuffer = fileobj.read(8192)
while len(readbuffer)!=0:
   gzipfile.write(readbuffer)
   zipfinal = zipfinal + zipbuffer.getvalue()
   zipbuffer.truncate(0)
   readbuffer = fileobj.read(8192)
      
print zipbuffer.getvalue()
print zipfinal

fileobj.close()



class UnbufferedGZIPContentProvider(object):
   def __init__(self):
      pass
      
   def __call__(self, filePath):
      return UnbufferedGZIPContent(filePath)
   

import gzip

class UnbufferedGZIPContent(object):
   def __init__(filePath):
      self._filePath = filePath
   
   def getContentLength(self):
      """
      returns content-length, None to omit 
      """  
      return None
   
   def getContentSize(self):
      """
      returns content-length, but compulsory to return correct value. Used for partial ranges
      raise ProcessRequestError(ProcessRequestErrorHandler.NOT_IMPLEMENTED) if ranges are not supported
      """
         
   def getContent(self, rangestart=None, rangeend=None):
            
   
   