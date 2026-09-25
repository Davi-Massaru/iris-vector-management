from . import auth,settings
from .sql import rows

def inspect():
    import iris
    version=iris.system.Version.GetVersion()
    verified = '2026.2 (Build 221U)' in version
    return {'instance':settings.INSTANCE,'version':version,'actor':auth.principal(),
            'namespaces':list(settings.NAMESPACES), 'roles':{'read':auth.allowed('VectorAdmin_Read'),
            'maintain':auth.allowed('VectorAdmin_Maintain'),'admin':auth.allowed('VectorAdmin_Admin')},
            'capabilities':{'catalog':verified,'vectorSearch':verified,'hnswCreate':verified and auth.allowed('VectorAdmin_Maintain'),
                            'configurationEditing':False,'rowMutation':False,'indexDrop':False,'indexRebuild':False},
            'prerequisite':None if verified else 'This installed build must pass the metadata and HNSW fixture gates.',
            'limits':{'pageSize':settings.MAX_PAGE_SIZE,'topK':settings.MAX_K,'previewValues':settings.PREVIEW_VALUES,
                      'querySeconds':settings.QUERY_SECONDS,'concurrentSearches':settings.CONCURRENT_SEARCHES},
            'csrf':auth.token({'kind':'csrf','actor':auth.principal()},3600)}

def require_verified():
    from .errors import Problem
    if not inspect()['capabilities']['catalog']:
        raise Problem('UNSUPPORTED_VERSION','The installed build has not passed the fixture gates.',422)
