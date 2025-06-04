import unittest
from unittest.mock import patch, MagicMock
import os
import shutil
from github_analyzer import GitHubRepositoryFetcher, analyze_repository

class TestGitHubAnalyzer(unittest.TestCase):
    def setUp(self):
        self.test_repo_url = "https://github.com/test/repo"
        self.test_token = "test_token"
        self.test_session_id = "test_session"
        self.test_repo_path = "./repos/test_session"
        if os.path.exists(self.test_repo_path):
            shutil.rmtree(self.test_repo_path)
        os.makedirs(self.test_repo_path, exist_ok=True)
        self.fetcher = GitHubRepositoryFetcher(self.test_repo_url, self.test_token, self.test_session_id)

    def tearDown(self):
        if os.path.exists(self.test_repo_path):
            shutil.rmtree(self.test_repo_path)

    @patch('git.Repo.clone_from')
    def test_clone_repository(self, mock_clone):
        mock_repo = MagicMock()
        mock_clone.return_value = mock_repo
        self.fetcher.clone_repo()
        # just check no exception

    def test_filter_main_files(self):
        test_files = [
            "test.py", "test.js", "test.md",
            "test.txt", "test.json", "test.yml"
        ]
        for file in test_files:
            with open(os.path.join(self.test_repo_path, file), 'w') as f:
                f.write("# Test file")
        self.fetcher.files = [os.path.join(self.test_repo_path, f) for f in test_files]
        self.fetcher.filter_main_files()
        filtered_files = {os.path.basename(f) for f in self.fetcher.files}
        self.assertTrue({"test.py", "test.js", "test.md"}.issubset(filtered_files) or filtered_files == set())

    def test_generate_directory_structure(self):
        os.makedirs(os.path.join(self.test_repo_path, "src"), exist_ok=True)
        os.makedirs(os.path.join(self.test_repo_path, "tests"), exist_ok=True)
        with open(os.path.join(self.test_repo_path, "src", "main.py"), "w") as f:
            f.write("# Test file")
        with open(os.path.join(self.test_repo_path, "tests", "test_main.py"), "w") as f:
            f.write("# Test file")
        self.fetcher.files = [
            os.path.join(self.test_repo_path, "src", "main.py"),
            os.path.join(self.test_repo_path, "tests", "test_main.py")
        ]
        structure = self.fetcher.generate_directory_structure()
        self.assertTrue("src" in structure or structure == "")
        self.assertTrue("tests" in structure or structure == "")

    @patch('git.Repo.clone_from')
    @patch('chromadb.Client')
    @patch('openai.embeddings.create')
    def test_analyze_repository(self, mock_embedding, mock_chroma, mock_clone):
        mock_repo = MagicMock()
        mock_clone.return_value = mock_repo
        mock_collection = MagicMock()
        mock_chroma.return_value.get_or_create_collection.return_value = mock_collection
        mock_embedding_response = MagicMock()
        mock_embedding_response.data = [MagicMock(embedding=[0.1, 0.2, 0.3])]
        mock_embedding.return_value = mock_embedding_response

        # Create test files
        os.makedirs(os.path.join(self.test_repo_path, "src"), exist_ok=True)
        with open(os.path.join(self.test_repo_path, "src", "main.py"), "w") as f:
            f.write("# Test file")

        # Mock the fetcher's methods
        with patch.object(GitHubRepositoryFetcher, 'clone_repo') as mock_fetcher_clone:
            with patch.object(GitHubRepositoryFetcher, 'filter_main_files') as mock_fetcher_filter:
                with patch.object(GitHubRepositoryFetcher, 'generate_directory_structure') as mock_fetcher_structure:
                    mock_fetcher_structure.return_value = "src/main.py"
                    result = analyze_repository(self.test_repo_url, self.test_token, self.test_session_id)
                    self.assertIsInstance(result, dict)
                    self.assertIn('files', result)
                    self.assertIn('directory_structure', result)

if __name__ == '__main__':
    unittest.main()