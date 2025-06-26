import unittest
import github_analyzer

class TestGithubAnalyzer(unittest.TestCase):
    def test_module_import(self):
        self.assertIsNotNone(github_analyzer)

if __name__ == "__main__":
    unittest.main() 