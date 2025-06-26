import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import unittest
import app

class TestApp(unittest.TestCase):
    def test_app_import(self):
        self.assertIsNotNone(app)

if __name__ == "__main__":
    unittest.main() 
