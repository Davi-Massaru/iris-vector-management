"""Compile-only validation shared by the editor and recipe publication."""
import ast

def validate(code):
    if not isinstance(code, str) or len(code) > 12000:
        return {'valid':False, 'message':'Código limitado a 12.000 caracteres.', 'line':1, 'column':1}
    try:
        tree = ast.parse(code)
        compile(tree, '<vector-generator>', 'exec')
    except (SyntaxError, ValueError) as exc:
        return {'valid':False, 'message':getattr(exc, 'msg', str(exc)),
                'line':getattr(exc, 'lineno', 1), 'column':getattr(exc, 'offset', 1)}
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom, ast.Global, ast.Nonlocal)):
            return {'valid':False, 'message':'Imports e estado global não são permitidos.', 'line':node.lineno, 'column':node.col_offset + 1}
    entry = next((n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'generate'), None)
    if not entry or [a.arg for a in entry.args.args] != ['row', 'context'] or entry.args.vararg or entry.args.kwarg or entry.args.kwonlyargs or entry.args.posonlyargs:
        return {'valid':False, 'message':'Defina generate(row, context).', 'line':getattr(entry, 'lineno', 1), 'column':1}
    return {'valid':True, 'message':'Sintaxe e assinatura válidas. Nenhum código foi executado.'}
