from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pytest
from qecflag.catalog import build_catalog

@pytest.fixture(scope='session')
def catalog():
    return build_catalog()
