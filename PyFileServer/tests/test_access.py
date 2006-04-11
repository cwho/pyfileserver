from paste.fixture import TestApp
from pyfileserver.wsgiapp import make_app

wsgi_app = make_app({})
app = TestApp(wsgi_app)

def test_app():
    app.get('/')
