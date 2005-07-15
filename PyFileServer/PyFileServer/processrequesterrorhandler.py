import os
import time
import HttpDateHelper


"""
WSGI Middleware component to catch ProcessRequestErrors and return a response based on the code.
"""

HTTP_NOT_MODIFIED = 304
HTTP_RANGE_NOT_SATISFIABLE = 416
HTTP_PRECONDITION_FAILED = 412
HTTP_NOT_IMPLEMENTED = 501
HTTP_BAD_REQUEST = 400
HTTP_NOT_FOUND = 404
HTTP_FORBIDDEN = 403
HTTP_METHOD_NOT_ALLOWED = 405
HTTP_INTERNAL_ERROR = 500

ERROR_DESCRIPTIONS = dict()

ERROR_DESCRIPTIONS[HTTP_NOT_MODIFIED] = "304 Not Modified"
ERROR_DESCRIPTIONS[HTTP_RANGE_NOT_SATISFIABLE] = "416 Range Not Satisfiable"
ERROR_DESCRIPTIONS[HTTP_PRECONDITION_FAILED] = "412 Precondition Failed"
ERROR_DESCRIPTIONS[HTTP_NOT_IMPLEMENTED] = "501 Not Implemented"
ERROR_DESCRIPTIONS[HTTP_BAD_REQUEST] = "400 Bad Request"
ERROR_DESCRIPTIONS[HTTP_METHOD_NOT_ALLOWED] = "405 Method Not Allowed"
ERROR_DESCRIPTIONS[HTTP_NOT_FOUND] = "404 Not Found"
ERROR_DESCRIPTIONS[HTTP_FORBIDDEN] = "403 Forbidden"
ERROR_DESCRIPTIONS[HTTP_INTERNAL_ERROR] = "500 Internal Server Error"

ERROR_RESPONSES = dict()
ERROR_RESPONSES[HTTP_BAD_REQUEST] = "An invalid request was specified"
ERROR_RESPONSES[HTTP_NOT_FOUND] = "The specified resource was not found"
ERROR_RESPONSES[HTTP_FORBIDDEN] = "Access denied to the specified resource"
ERROR_RESPONSES[HTTP_INTERNAL_ERROR] = "An internal server error occured"

class ProcessRequestError(Exception):
   def __init__(self, value):
      self.value = value
   def __str__(self):
      return repr(self.value)  
      
      
      
class ErrorPrinter(object):
   def __init__(self, application, server_descriptor=None):
      self._application = application
      self._server_descriptor = server_descriptor
      
   def __call__(self, environ, start_response):
      try:
         try:
            return self._application(environ, start_response)
         except ProcessRequestError, e:
            raise
# Catch all exceptions to return as 500 Internal Error - disabled for debugging
#         except:
#            raise ProcessRequestError(500)
      except ProcessRequestError, e:
         evalue = e.value
         if evalue in ERROR_DESCRIPTIONS:
            respcode = ERROR_DESCRIPTIONS[evalue]
         else:
            respcode = str(evalue)

         if evalue in ERROR_RESPONSES:                  
            start_response(respcode, [('Content-Type', 'text/html'), ('Date',HttpDateHelper.getstrftime())])
            
            respbody = '<html><head><title>' + respcode + '</title></head><body><H1>' + respcode + '</H1>' 
            respbody = respbody + ERROR_RESPONSES[evalue] + '<HR>'         
            if self._server_descriptor:
               respbody = respbody + self._server_descriptor + '<BR>'
            respbody = respbody + HttpDateHelper.getstrftime() + '</body></html>'        

            return [respbody] 
         else:
            start_response(respcode, [('Content-Type', 'text/html'), ('Content-Length', '0'), ('Date',HttpDateHelper.getstrftime())])
            return ['']
     