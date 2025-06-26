import unittest
import chat_memory

class TestChatMemory(unittest.TestCase):
    def test_module_import(self):
        self.assertIsNotNone(chat_memory)

if __name__ == "__main__":
    unittest.main() 