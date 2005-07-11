import os
import time
"""
WSGI Middleware component to catch ProcessRequestErrors and return a response based on the code.
"""


HTTP_NOT_FOUND = 404
HTTP_FORBIDDEN = 403
HTTP_INTERNAL_ERROR = 500

ERROR_DESCRIPTIONS = dict()
ERROR_DESCRIPTIONS[HTTP_NOT_FOUND] = "404 Not Found"
ERROR_DESCRIPTIONS[HTTP_FORBIDDEN] = "403 Forbidden"
ERROR_DESCRIPTIONS[HTTP_INTERNAL_ERROR] = "500 Internal Server Error"

ERROR_RESPONSES = dict()
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
         return self._application(environ, start_response)
      except ProcessRequestError, e:
         evalue = e.value
         if evalue in ERROR_DESCRIPTIONS:
            respcode = ERROR_DESCRIPTIONS[evalue]
         else:
            evalue = HTTP_INTERNAL_ERROR
            respcode = "500 Internal Server Error"
                  
         start_response(respcode, [('Content-type', 'text/html')])
         
         respbody = '<html><head><title>' + respcode + '</title></head><body><H1>' + respcode + '</H1>' 
         if evalue in ERROR_RESPONSES:
            respbody = respbody + ERROR_RESPONSES[evalue] + '<HR>'
         else:
            respbody = respobdy + "Error<HR>" 
         
         if self._server_descriptor:
            respbody = respbody + self._server_descriptor + '<BR>'
         respbody = respbody + time.asctime(time.localtime()) + ' GMT</body></html>'        
         return [respbody] 

     