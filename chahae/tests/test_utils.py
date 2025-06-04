import unittest
import os
import json
from datetime import datetime

class TestUtils(unittest.TestCase):
    def setUp(self):
        self.test_dir = "test_data"
        os.makedirs(self.test_dir, exist_ok=True)

    def tearDown(self):
        # 테스트 디렉토리 정리
        if os.path.exists(self.test_dir):
            for file in os.listdir(self.test_dir):
                os.remove(os.path.join(self.test_dir, file))
            os.rmdir(self.test_dir)

    def test_create_status_file(self):
        """상태 파일 생성 및 업데이트 테스트"""
        status_file = os.path.join(self.test_dir, "status.json")
        
        # 초기 상태 생성
        initial_status = {
            "status": "처리 중",
            "timestamp": datetime.now().isoformat(),
            "progress": 0
        }
        
        with open(status_file, 'w') as f:
            json.dump(initial_status, f)
        
        # 파일 생성 확인
        self.assertTrue(os.path.exists(status_file))
        
        # 상태 업데이트
        updated_status = {
            "status": "완료",
            "timestamp": datetime.now().isoformat(),
            "progress": 100
        }
        
        with open(status_file, 'w') as f:
            json.dump(updated_status, f)
        
        # 업데이트 확인
        with open(status_file, 'r') as f:
            current_status = json.load(f)
            self.assertEqual(current_status["status"], "완료")
            self.assertEqual(current_status["progress"], 100)

    def test_validate_repo_url(self):
        """저장소 URL 유효성 검사 테스트"""
        valid_urls = [
            "https://github.com/username/repo",
            "https://github.com/username/repo.git",
            "git@github.com:username/repo.git"
        ]
        
        invalid_urls = [
            "잘못된 URL",
            "http://not-github.com/repo",
            "github.com/username/repo"
        ]
        
        for url in valid_urls:
            self.assertTrue(self.is_valid_repo_url(url))
            
        for url in invalid_urls:
            self.assertFalse(self.is_valid_repo_url(url))

    def test_validate_file_extension(self):
        """파일 확장자 유효성 검사 테스트"""
        valid_extensions = [".py", ".js", ".md", ".json", ".yml", ".yaml"]
        invalid_extensions = [".txt", ".doc", ".pdf", ".exe"]
        
        for ext in valid_extensions:
            self.assertTrue(self.is_valid_file_extension(ext))
            
        for ext in invalid_extensions:
            self.assertFalse(self.is_valid_file_extension(ext))

    @staticmethod
    def is_valid_repo_url(url):
        """저장소 URL 유효성 검사 헬퍼 메서드"""
        return (
            url.startswith("https://github.com/") or
            url.startswith("git@github.com:") or
            url.endswith(".git")
        )

    @staticmethod
    def is_valid_file_extension(extension):
        """파일 확장자 유효성 검사 헬퍼 메서드"""
        valid_extensions = {".py", ".js", ".md", ".json", ".yml", ".yaml"}
        return extension.lower() in valid_extensions

if __name__ == '__main__':
    unittest.main() 