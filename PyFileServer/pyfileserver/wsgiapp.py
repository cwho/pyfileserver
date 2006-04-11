import os
import pyfileserver.mainappwrapper as main
from paste.deploy.converters import asbool
from paste.util import import_string

def make_app(global_conf, verbose=0,
             data_dir=None,
             locks_file=None,
             locks_manager=None,
             props_file=None,
             props_manager=None,
             domain_controller=None,
             **kw):

    all_conf = global_conf.copy()
    all_conf.update(kw)
    server_info = {}
    for name, value in kw.items():
        if name.startswith('server_info'):
            new_name = name[len('server_info'):]
            new_name = new_name.lstrip().lstrip('.')
            del kw[name]
            server_info[new_name] = value
    try:
        verbose = int(verbose)
    except ValueError:
        verbose = asbool(verbose)
    data_dir = data_dir or os.getcwd()
    locks_file = locks_file or os.path.join(data_dir, 'PyFileServer.locks')
    props_file = props_file or os.path.join(data_dir, 'PyFileServer.dat')
    locks_manager = make_object(
        locks_manager, main.LockManager, locks_file)
    props_manager = make_object(
        props_manager, main.PropertyManager, props_file)
    domain_controller = make_object(
        domain_controller, main.PyFileServerDomainController)
    return main.PyFileApp(
        verbose=verbose,
        locks_manager=locks_manager,
        props_manager=props_manager,
        domain_controller=domain_controller,
        server_info=server_info)

def make_object(value, default, *args, **kw):
    if not value:
        return default(*args, **kw)
    elif isinstance(value, basestring):
        return import_string.eval_import(value)
    else:
        return value
