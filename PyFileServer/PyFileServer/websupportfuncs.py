import os
import sys

URL_SEP = '/'

def recursiveGetPath(dirtorecurs, displaypath, recursfurther, liststore, preadd=True):   
   filelist = os.listdir(dirtorecurs)
   for f in filelist:
      filename = os.path.join(dirtorecurs, f)
      if os.path.isdir(filename):
         filedisplaypath = displaypath + f + URL_SEP
         if preadd:
            liststore.append( (filename , filedisplaypath) )
         if recursfurther:
            recursiveGetPath(filename, filedisplaypath, recursfurther, liststore, preadd)
         if not preadd:
            liststore.append( (filename , filedisplaypath) )
      else: #file
         filedisplaypath = displaypath + f
         liststore.append( (filename , filedisplaypath) )


def getDepthActionList(mappedpath, displaypath, depthlevel, preadd=True):
   if os.path.isdir(mappedpath) or depthlevel == '0':
      liststore = [] 
      if preadd:
         liststore.append((mappedpath,displaypath))
      recursiveGetPath(mappedpath, displaypath, depthlevel == 'infinity', liststore, preadd)
      if not preadd:
         liststore.append((mappedpath,displaypath))
      return liststore         
   else:
      return [(mappedpath, displaypath)]



