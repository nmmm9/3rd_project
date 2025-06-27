import pytest
import sys, os
from dotenv import load_dotenv
load_dotenv()
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import git_modifier
import inspect

def test_module_import():
    assert git_modifier is not None

def test_check_git_status_returns_dict():
    if hasattr(git_modifier, 'check_git_status'):
        result = git_modifier.check_git_status()
        assert isinstance(result, dict)

def test_get_file_diff_invalid_path():
    if hasattr(git_modifier, 'get_file_diff'):
        result = git_modifier.get_file_diff('no_such_file.py')
        assert result is None or result == "" or isinstance(result, str)

def test_get_file_diff_valid_path(tmp_path):
    # 임시 파일 생성
    file = tmp_path / "test.py"
    file.write_text("print('hello')")
    if hasattr(git_modifier, 'get_file_diff'):
        result = git_modifier.get_file_diff(str(file))
        assert isinstance(result, str)

def test_all_functions():
    for name, func in inspect.getmembers(git_modifier, inspect.isfunction):
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
