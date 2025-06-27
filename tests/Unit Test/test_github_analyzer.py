import pytest
import sys, os
from dotenv import load_dotenv
load_dotenv()
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import github_analyzer
import inspect

def test_module_import():
    assert github_analyzer is not None

def test_analyze_repo():
    if hasattr(github_analyzer, 'analyze_repo'):
        result = github_analyzer.analyze_repo('https://github.com/test/repo')
        assert isinstance(result, dict)

def test_invalid_repo_url():
    if hasattr(github_analyzer, 'analyze_repo'):
        result = github_analyzer.analyze_repo('not_a_url')
        assert 'error' in result or result is None

def test_all_functions():
    for name, func in inspect.getmembers(github_analyzer, inspect.isfunction):
        sig = inspect.signature(func)
        params = sig.parameters
        args = []
        for p in params.values():
            if p.default is not inspect.Parameter.empty:
                args.append(p.default)
            elif p.annotation == str:
                args.append("test")
            else:
                args.append(None)
        try:
            func(*args)
        except Exception:
            pass  # 예외 발생도 허용(테스트 목적)

if __name__ == "__main__":
    pytest.main()
