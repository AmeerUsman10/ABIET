import pytest
import sys
import pathlib

# Add project root to PYTHONPATH
project_root = pathlib.Path(__file__).parent.parent
sys.path.insert(0, str(project_root))