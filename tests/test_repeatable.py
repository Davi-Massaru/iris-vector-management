import unittest
from vector_admin.generators import validate
from vector_admin.seed_runner import should_generate

class RepeatableTests(unittest.TestCase):
    def test_policies(self):
        for policy in ('ALL','CHANGED','MISSING'):
            self.assertTrue(should_generate(policy,False,['s','g'],'s','g'))
        self.assertTrue(should_generate('ALL',True,['s','g'],'s','g'))
        self.assertFalse(should_generate('MISSING',True,None,'s','g'))
        self.assertFalse(should_generate('CHANGED',True,['s','g'],'s','g'))
        self.assertTrue(should_generate('CHANGED',True,['old','g'],'s','g'))
        self.assertTrue(should_generate('CHANGED',True,['s','old'],'s','g'))
        self.assertTrue(should_generate('CHANGED',True,None,'s','g'))

    def test_syntax_reports_location_without_executing(self):
        self.assertTrue(validate('def generate(row, context):\n    raise RuntimeError("must not execute")')['valid'])
        result=validate('def generate(row, context):\n    return [1,,2]')
        self.assertFalse(result['valid']); self.assertEqual(result['line'],2)
        self.assertFalse(validate('return 1')['valid'])
        self.assertFalse(validate('def generate(row):\n    return []')['valid'])
        self.assertFalse(validate('import os\ndef generate(row, context):\n    return []')['valid'])

if __name__=='__main__': unittest.main()
