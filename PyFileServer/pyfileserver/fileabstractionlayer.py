import os
import sys
import md5
import mimetypes
import shutil
import stat

from processrequesterrorhandler import HTTPRequestException
import processrequesterrorhandler

BUFFER_SIZE = 8192

class FilesystemAbstractionLayer(object):
   
   def getResourceDescription(self, respath):
      if os.path.isdir(respath):
         return "Directory"
      elif os.path.isfile(respath):
         return "File"
      else:
         return "Unknown"

   def getContentType(self, respath):
      if os.path.isfile(respath):
         (mimetype, mimeencoding) = mimetypes.guess_type(respath); 
         if mimetype == '' or mimetype is None:
            mimetype = 'application/octet-stream' 
         return mimetype
      else:
         return "text/html"

   def getLastModified(self, respath):
         statresults = os.stat(respath)
         return statresults[stat.ST_MTIME]      
   
   def getContentLength(self, respath):
      if not os.path.isfile(respath):
         return 0
      else:
         statresults = os.stat(respath)
         return statresults[stat.ST_SIZE]      
   
   def getEntityTag(self, respath):
      if not os.path.isfile(respath):
         return md5.new(respath).hexdigest()   
      if sys.platform == 'win32':
         statresults = os.stat(respath)
         return md5.new(respath).hexdigest() + '-' + str(statresults[stat.ST_MTIME]) + '-' + str(statresults[stat.ST_SIZE])
      else:
         statresults = os.stat(respath)
         return str(statresults[stat.ST_INO]) + '-' + str(statresults[stat.ST_MTIME]) + '-' + str(statresults[stat.ST_SIZE])

   def isCollection(self, respath):
      return os.path.isdir(respath)
   
   def isResource(self, respath):
      return os.path.isfile(respath)
   
   def exists(self, respath):
      return os.path.exists(respath)
   
   def createCollection(self, respath):
      os.mkdir(respath)
   
   def deleteCollection(self, respath):
      os.rmdir(respath)
   
   def supportRanges(self):
      return True
   
   def openResourceForRead(self, respath):
      mime = self.getContentType(respath)
      if mime.startswith("text"):
         return file(respath, 'r', BUFFER_SIZE)
      else:
         return file(respath, 'rb', BUFFER_SIZE)
   
   def openResourceForWrite(self, respath, contenttype=None):
      if contenttype is None:
         istext = False
      else:
         istext = contenttype.startswith("text")            
      if istext:
         return file(respath, 'w', BUFFER_SIZE)
      else:
         return file(respath, 'wb', BUFFER_SIZE)
   
   def deleteResource(self, respath):
      os.unlink(respath)
   
   def copyResource(self, respath, destrespath):
      shutil.copy2(respath, destrespath)
   
   def getContainingCollection(self, respath):
      return os.path.dirname(respath)
   
   def getCollectionContents(self, respath):
      return os.listdir(respath)
      
   def joinPath(self, rescollectionpath, resname):
      return os.path.join(rescollectionpath, resname)

   def splitPath(self, respath):
      return os.path.split(respath)

   def writeProperty(self, respath, propertyname, propertyns, propertyvalue):
      raise HTTPRequestException(processrequesterrorhandler.HTTP_CONFLICT)               

   def removeProperty(self, respath, propertyname, propertyns):
      raise HTTPRequestException(processrequesterrorhandler.HTTP_CONFLICT)               

   def getProperty(self, respath, propertyname, propertyns):
      if propertyns == 'DAV:':
         isfile = os.path.isfile(respath)
         if propertyname == 'creationdate':
             statresults = os.stat(respath)
             return httpdatehelper.getstrftime(statresults[stat.ST_CTIME])
         elif propertyname == 'getcontenttype':
             return self.getContentType(respath)
         elif propertyname == 'resourcetype':
            if os.path.isdir(respath):
               return '<D:collection />'            
            else:
               return ''   
         elif propertyname == 'getlastmodified':
            statresults = os.stat(respath)
            return httpdatehelper.getstrftime(statresults[stat.ST_MTIME])
         elif propname == 'getcontentlength':
            if isfile:
               statresults = os.stat(respath)
               return str(statresults[stat.ST_SIZE])
            raise HTTPRequestException(processrequesterrorhandler.HTTP_NOT_FOUND)               
         elif propertyname == 'getetag':
            return self.getEntityTag(respath)
      raise HTTPRequestException(processrequesterrorhandler.HTTP_NOT_FOUND)               
   
   def isPropertySupported(self, respath, propertyname, propertyns):
      supportedliveprops = ['creationdate', 'getcontenttype','resourcetype','getlastmodified', 'getcontentlength', 'getetag']
      if propertyns != "DAV:" or propertyname not in supportedliveprops:
         return False      
      return True
   
   def getSupportedPropertyNames(self, respath):
      appProps = []
      #DAV properties for all resources
      appProps.append( ('DAV:','creationdate') )
      appProps.append( ('DAV:','displayname') )
      appProps.append( ('DAV:','getcontenttype') )
      appProps.append( ('DAV:','resourcetype') )
      appProps.append( ('DAV:','getlastmodified') )   
      if os.path.isfile(respath):
         appProps.append( ('DAV:','getcontentlength') )
         appProps.append( ('DAV:','getetag') )
      return appProps
   
   def resolvePath(self, resheadpath, urlelementlist):
      relativepath = os.sep.join(urlelementlist)
      if relativepath.endswith(os.sep):
         relativepath = relativepath[:-len(os.sep)] # remove suffix os.sep since it causes error (SyntaxError) with os.path functions
     
      normrelativepath = ''
      if relativepath != '':          # avoid adding of .s
         normrelativepath = os.path.normpath(relativepath)   

      return resheadpath + os.sep + normrelativepath

   def breakPath(self, resheadpath, respath):      
      relativepath = respath[len(resheadpath):].strip(os.sep)
      return relativepath.split(os.sep)

      