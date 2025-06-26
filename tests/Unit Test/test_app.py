import unittest
import app

class TestApp(unittest.TestCase):
    def test_app_import(self):
        self.assertIsNotNone(app)

if __name__ == "__main__":
    unittest.main() 