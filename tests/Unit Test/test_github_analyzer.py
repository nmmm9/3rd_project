import unittest
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import github_analyzer

class TestGithubAnalyzer(unittest.TestCase):
    def test_module_import(self):
        self.assertIsNotNone(github_analyzer)

    # 예시: 주요 분석 함수가 있다면 테스트
    def test_analyze_repo(self):
        if hasattr(github_analyzer, 'analyze_repo'):
            result = github_analyzer.analyze_repo('https://github.com/test/repo')
            self.assertIsInstance(result, dict)

    # 예외 상황 테스트 (예: 잘못된 URL)
    def test_invalid_repo_url(self):
        if hasattr(github_analyzer, 'analyze_repo'):
            result = github_analyzer.analyze_repo('not_a_url')
            self.assertTrue('error' in result or result is None)

if __name__ == "__main__":
    unittest.main()
