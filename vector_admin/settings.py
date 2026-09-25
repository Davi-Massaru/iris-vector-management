import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INSTANCE = 'local'
NAMESPACES = tuple(x.strip().upper() for x in os.getenv('VECTOR_ADMIN_NAMESPACES', 'USER').split(',') if x.strip())
ADMIN_NAMESPACE = os.getenv('VECTOR_ADMIN_NAMESPACE', 'USER')
SYSADMIN_URL = os.getenv('VECTOR_ADMIN_SYSADMIN_URL', 'http://127.0.0.1:52773/api/admin')
PAGE_SIZE = 25
MAX_PAGE_SIZE = 100
MAX_K = 100
MAX_BODY = 131072
MAX_DIMENSIONS = 16384
PREVIEW_VALUES = 32
TEXT_LIMIT = 1200
QUERY_SECONDS = 10
CONCURRENT_SEARCHES = 2
CONTRACT = json.loads((ROOT / 'vendor/sysadmin-allowlist.json').read_text(encoding='utf-8'))

