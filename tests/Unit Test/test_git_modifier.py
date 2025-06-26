import unittest
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import git_modifier

class TestGitModifier(unittest.TestCase):
    def test_module_import(self):
        self.assertIsNotNone(git_modifier)

    # 예시: git 관련 함수가 있다면 테스트
    def test_check_git_status(self):
        if hasattr(git_modifier, 'check_git_status'):
            result = git_modifier.check_git_status()
            self.assertIsInstance(result, dict)

    # 예외 상황 테스트 (예: 잘못된 경로)
    def test_invalid_path(self):
        if hasattr(git_modifier, 'get_file_diff'):
            result = git_modifier.get_file_diff('no_such_file.py')
            self.assertTrue(result is None or result == "" or isinstance(result, str))

if __name__ == "__main__":
    unittest.main()
