import json
import time
import uuid
from . import auth,settings
from .sql import namespace,rows

def record(action,target,state,evidence=None):
    # All callers pass structured operational metadata, never SQL arguments or records.
    safe = {k:v for k,v in (evidence or {}).items() if k in ('code','operation','fingerprint','diagnosis')}
    with namespace(settings.ADMIN_NAMESPACE):
        rows('INSERT INTO VectorAdmin.Audit (EventId,Actor,Action,Target,State,CreatedAt,Evidence) VALUES (?,?,?,?,?,?,?)',
             (uuid.uuid4().hex,auth.principal(),action,str(target)[:512],state,time.time(),json.dumps(safe)),limit=0)

