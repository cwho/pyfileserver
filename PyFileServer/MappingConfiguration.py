"""
Temporary. This will probably become a config file that is read/cached as dict. Like ConfigParser
"""

def getConfiguration():

   dictConfig = dict()
   dictConfig['MapKeysCaseSensitive'] = 1
   dictConfig['AllowRelativePaths'] = 1

   mapConfig = dict()
   mapConfig['/cwho'] = 'C:\\SoC\\WSGIUtils'
   mapConfig['/cwho/ext2'] = 'C:\\SoC\\Data\\Sample2'   
   dictConfig['config_mapping'] = mapConfig

   dictConfig['Info_AdminEmail'] = 'fuzzybr80@gmail.com'
   dictConfig['Info_Organization'] = 'Google\'s Summer of Code Project - http://cwho.blogspot.com/'
   
   return dictConfig