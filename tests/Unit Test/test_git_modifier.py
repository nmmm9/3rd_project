import unittest
import git_modifier

class TestGitModifier(unittest.TestCase):
    def test_module_import(self):
        self.assertIsNotNone(git_modifier)

if __name__ == "__main__":
    unittest.main() 