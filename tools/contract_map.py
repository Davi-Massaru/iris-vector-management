"""Generate the read-only administrative allowlist from the pinned contract."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = json.loads((ROOT / 'vendor/mainspec_v2.json').read_text())
paths = ['/info', '/v2/databases', '/v2/database', '/v2/namespaces', '/v2/namespace',
         '/v2/namespace/global-mappings', '/v2/namespace/package-mappings',
         '/v2/namespace/routine-mappings', '/v2/tasks', '/v2/task',
         '/v2/task/info', '/v2/task/upcoming', '/v2/task/history',
         '/v2/task/manager']

def resolve(value):
    if isinstance(value, dict):
        if '$ref' in value:
            target = spec
            for part in value['$ref'].split('/')[1:]:
                target = target[part]
            return resolve(target)
        return {k: resolve(v) for k, v in value.items()}
    if isinstance(value, list):
        return [resolve(v) for v in value]
    return value

result = {}
lines = ['# SysAdmin API map', '', 'Pinned revision: `' + (ROOT / 'vendor/sysadmin-revision.txt').read_text().strip() + '`',
         '', 'Base URL: `/api/admin`. Generated from the checked-in contract. Authentication must be verified separately on the installed instance.', '']
for path in paths:
    definition = spec['paths'][path]
    operation = definition['get']
    entry = {'method': 'GET', 'path': path, 'privileges': operation['summary'],
             'parameters': resolve(definition.get('parameters', []) + operation.get('parameters', [])),
             'response': resolve(operation['responses']['200'])}
    result[path] = entry
    lines += ['## GET ' + path, '', operation['summary'], '', '```json', json.dumps(entry, indent=2), '```', '']
definition = spec['paths']['/v2/task']
operation = definition['post']
entry = {'method':'POST','path':'/v2/task','privileges':operation['summary'],'parameters':[],
         'request':resolve(operation['requestBody']),'response':resolve(operation['responses']['201'])}
result['POST /v2/task'] = entry
lines += ['## POST /v2/task','',operation['summary'],'','```json',json.dumps(entry,indent=2),'```','']
definition = spec['paths']['/v2/task/run']; operation=definition['post']
entry={'method':'POST','path':'/v2/task/run','privileges':operation['summary'],
       'parameters':resolve(definition.get('parameters',[])+operation.get('parameters',[])),
       'request':resolve(operation['requestBody']),'response':resolve(operation['responses']['200'])}
result['POST /v2/task/run']=entry
lines += ['## POST /v2/task/run','',operation['summary'],'','```json',json.dumps(entry,indent=2),'```','']
(ROOT / 'docs/sysadmin-api-map.md').write_text('\n'.join(lines), encoding='utf-8')
(ROOT / 'vendor/sysadmin-allowlist.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
