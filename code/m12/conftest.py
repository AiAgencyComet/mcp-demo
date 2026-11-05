"""Shared test setup for module 12. The Fernhill server is imported from code/fernhill (not copied, not changed)."""
import copy
import os
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "fernhill"))   # server.py, shop.py
sys.path.insert(0, str(HERE))                       # releases/, ship/

import shop  # noqa: E402


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def fresh_shop():
    """shop.ORDERS is a module global. place_order adds to it and the next order ID is 1041 + len(ORDERS).
    Without this reset, test order changes the IDs that later tests see."""
    if os.environ.get("M12_NO_RESET"):   # demo switch: show what breaks without the reset
        yield
        return
    saved = copy.deepcopy(shop.ORDERS)
    yield
    shop.ORDERS.clear()
    shop.ORDERS.update(saved)
