"""Pytest configuration and environment setup."""

import sys
from pathlib import Path


# Add project root directory to sys.path for test environment
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
