
"""
The PyFileServerDomainController fulfills the requirements of a DomainController as used for authentication
with httpauthentication.HTTPAuthenticator
"""

class PyFileServerDomainController(object):
    def __init__(self, srvconfig):
        self._srvconfig = srvconfig
           
    def getDomainRealm(self, inputURL, environ):
        # we don't get the realm here, its already been resolved in requestresolve 
        return environ['pyfileserver.mappedrealm']   
    
    def getDomainUsers(self, realmname):
        if realmname in self._srvconfig['user_mapping']:
            return self._srvconfig['user_mapping'][realmname]
        else:
            return None
      
    def authDomainUser(self, realmname, username, password):
        if realmname in self._srvconfig['user_mapping']:
            if username in self._srvconfig['user_mapping'][realmname]:
                if self._srvconfig['user_mapping'][realmname][username] == password:
                    return True
            return False
        else:
            return True
            