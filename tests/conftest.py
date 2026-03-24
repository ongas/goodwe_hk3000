"""Pytest configuration for HK3000 tests."""

import sys
from pathlib import Path

# Add custom_components directory to Python path
custom_components_path = Path(__file__).parent.parent / "custom_components"
sys.path.insert(0, str(custom_components_path))
