import runpy
import traceback
import sys
try:
    runpy.run_path('/workspace/tools/acceptance.py')
except Exception:
    traceback.print_exc(file=sys.stdout)
    raise
