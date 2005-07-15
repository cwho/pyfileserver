import random
import base64
import md5
import time
import re

"""
Sample Domain Controller - this allows "plugin" of domain information to the Digest Authenticator
"""
class SimpleDomainController(object):
    def __init__(self):
        pass
           
    def getDomainRealm(self, inputURL, environ=None):
        """
        Returns a tuple of Domain Name, Domain Dictionary
        Domain Name is a string
        Domain Dictionary is a dictionary of username keys and password values as strings
        """
        return "SampleDomain" 
    
    def getDomainUsers(self, realmname):
        return dict({"John Smith" : "YouNeverGuessMe"})
      
    def authDomainUser(self, realmname, username, password):
        if username == 'John Smith' and password == 'YouNeverGuessMe':
            return True
        else:
            return False   
              
       
class HTTPAuthenticator(object):

    def __init__(self, application, domaincontroller, acceptbasic, acceptdigest, defaultdigest):
        self._domaincontroller = domaincontroller
        self._application = application
        self._noncedict = dict([])
        self._headerparser = re.compile("([\w]+)=([^,]*),")
        self._headermethod = re.compile("^([\w]+)")
        
        self._acceptbasic = acceptbasic
        self._acceptdigest = acceptdigest
        self._defaultdigest = defaultdigest
   
    def __call__(self, environ, start_response):
        realmname = self._domaincontroller.getDomainRealm(environ['PATH_INFO'] , environ)
        dictUsers = self._domaincontroller.getDomainUsers(realmname)
        if not dictUsers:       # no users specified, no authentication needed
            environ['httpauthentication.realm'] = realmname
            environ['httpauthentication.username'] = ''
            return self._application(environ, start_response)
        
        if 'HTTP_AUTHORIZATION' in environ:
            authheader = environ['HTTP_AUTHORIZATION'] 
            authmatch = self._headermethod.search(authheader)          
            authmethod = "None"
            if authmatch:
                authmethod = authmatch.group(1).lower()
            if authmethod == 'digest' and self._acceptdigest:
                return self.authDigestAuthRequest(environ, start_response)
            elif authmethod == 'basic' and self._acceptbasic:
                return self.authBasicAuthRequest(environ, start_response)
            else:
                start_response("400 Bad Request", [('Content-Length', 0)])
                return ['']                           
        else:
            if self._defaultdigest:
                return self.sendDigestAuthResponse(environ, start_response)
            else:
                return self.sendBasicAuthResponse(environ, start_response)

        #should not get here, failsafe response
        start_response("400 Bad Request", [('Content-Length', 0)])
        return ['']        

    def sendBasicAuthResponse(self, environ, start_response):
        realmname = self._domaincontroller.getDomainRealm(environ['PATH_INFO'] , environ)
        wwwauthheaders = "Basic realm=\"" + realmname + "\"" 
        start_response("401 Not Authorized", [('WWW-Authenticate', wwwauthheaders)])
        return ['']

    def authBasicAuthRequest(self, environ, start_response):
        realmname = self._domaincontroller.getDomainRealm(environ['PATH_INFO'] , environ)
        authheader = environ['HTTP_AUTHORIZATION']
        authvalue = ''
        try:
            authvalue = authheader[len("Basic "):]
        except:
            authvalue = ''
        authvalue = authvalue.strip().decode('base64')
        username, password = authvalue.split(':',1)
        
        if self._domaincontroller.authDomainUser(realmname, username, password):
            environ['httpauthentication.realm'] = realmname
            environ['httpauthentication.username'] = username
            return self._application(environ, start_response)
        else:
            return self.sendBasicAuthResponse(environ, start_response)
        
    def sendDigestAuthResponse(self, environ, start_response):    

        realmname = self._domaincontroller.getDomainRealm(environ['PATH_INFO'] , environ)

        random.seed()
        serverkey = hex(random.getrandbits(32))[2:]
        etagkey = md5.new(environ['PATH_INFO']).hexdigest()
        timekey = str(time.time())  
        nonce = base64.b64encode(timekey + md5.new(timekey + ":" + etagkey + ":" + serverkey).hexdigest())
        wwwauthheaders = "Digest realm=\"" + realmname + "\", nonce=\"" + nonce + \
            "\", algorithm=\"MD5\", qop=\"auth\""                 
#        print "Send:", wwwauthheaders
        responseHeaders = []
        responseHeaders.append(('WWW-Authenticate', wwwauthheaders))
        start_response("401 Not Authorized", responseHeaders)
        return ['']
        
    def authDigestAuthRequest(self, environ, start_response):  

        realmname = self._domaincontroller.getDomainRealm(environ['PATH_INFO'] , environ)
        dictUsers = self._domaincontroller.getDomainUsers(realmname)
        
        isinvalidreq = False
        httpallowed = True
         
        authheaderdict = dict([])
        authheaders = environ['HTTP_AUTHORIZATION'] + ','
        if not authheaders.lower().strip().startswith("digest"):
            isinvalidreq = True
        authheaderlist = self._headerparser.findall(authheaders)
        for authheader in authheaderlist:
            authheaderkey = authheader[0]
            authheadervalue = authheader[1].strip().strip("\"")
            authheaderdict[authheaderkey] = authheadervalue
#            print "\t" + authheaderkey + ":" + authheadervalue
         
        if 'username' in authheaderdict:
            req_username = authheaderdict['username']
            if req_username not in dictUsers:
                httpallowed = False
        else:
            isinvalidreq = True

        if 'realm' in authheaderdict:
            if authheaderdict['realm'].upper() != realmname.upper():
                isinvalidreq = True
        
        if 'algorithm' in authheaderdict:
            if authheaderdict['algorithm'].upper() != "MD5":
                isinvalidreq = True         # only MD5 supported
        
        if 'uri' in authheaderdict:
            req_uri = authheaderdict['uri']

        if 'nonce' in authheaderdict:
            req_nonce = authheaderdict['nonce']
        else:
            isinvalidreq = True

        req_hasqop = False
        if 'qop' in authheaderdict:
            req_hasqop = True
            req_qop = authheaderdict['qop']     
            if req_qop.lower() != "auth":
                isinvalidreq = True   # only auth supported, auth-int not supported        
        else:
            req_qop = None

        if 'cnonce' in authheaderdict:
            req_cnonce = authheaderdict['cnonce']
        else:
            req_cnonce = None
            if req_hasqop:
                isinvalidreq = True
         
        if 'nc' in authheaderdict:    # is read but nonce-count checking not implemented
            req_nc = authheaderdict['nc']
        else:
            req_nc = None
            if req_hasqop:
                isinvalidreq = True

        if 'response' in authheaderdict:
            req_response = authheaderdict['response']
        else:
            isinvalidreq = True

        if isinvalidreq:
            start_response("400 Bad Request", [('Content-Length', 0)])
            return ['']
             
        if httpallowed:
            req_password = dictUsers[req_username]
            req_method = environ['REQUEST_METHOD']
             
            required_digest = self.computeDigestResponse(req_username, realmname, req_password, req_method, req_uri, req_nonce, req_cnonce, req_qop, req_nc)
            if required_digest != req_response:
                httpallowed = False

        if httpallowed:
            environ['httpauthentication.realm'] = realmname
            environ['httpauthentication.username'] = req_username
            return self._application(environ, start_response)                
     
        return self.sendDigestAuthResponse(environ, start_response)

    def computeDigestResponse(self, username, realm, password, method, uri, nonce, cnonce, qop, nc):
        A1 = username + ":" + realm + ":" + password
        A2 = method + ":" + uri
        if qop:
            digestresp = self.md5kd( self.md5h(A1), nonce + ":" + nc + ":" + cnonce + ":" + qop + ":" + self.md5h(A2))
        else:
            digestresp = self.md5kd( self.md5h(A1), nonce + ":" + self.md5h(A2))
        return digestresp
                
    def md5h(self, data):
        return md5.new(data).hexdigest()
        
    def md5kd(self, secret, data):
        return self.md5h(secret + ':' + data)