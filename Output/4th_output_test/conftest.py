import pytest
from dotenv import load_dotenv

# Load environment variables from .env file before running tests
load_dotenv()

@pytest.fixture(autouse=True)
def setup_test_env():
    # Any test setup can go here
    pass 