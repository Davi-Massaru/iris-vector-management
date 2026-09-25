import json
from .sql import rows

PUBLIC_SETTINGS = {'modelName', 'maxTokens', 'checkTokenCount'}

def sanitize(raw):
    try:
        data = json.loads(raw)
        if not isinstance(data, dict):
            return {}
        return {k: v for k, v in data.items() if k in PUBLIC_SETTINGS and isinstance(v, (str, int, float, bool)) and len(str(v)) <= 256}
    except (ValueError, TypeError):
        return {}

def list_configs():
    return [{'name': r[0], 'provider': r[1], 'dimensions': r[2], 'settings': sanitize(r[3])}
            for r in rows('SELECT TOP 101 Name, EmbeddingClass, VectorLength, Configuration FROM %Embedding.Config ORDER BY Name', limit=101)]
