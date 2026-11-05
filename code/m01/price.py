"""One shop function, used by all three ways."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "fernhill"))
import shop

def get_price(drink: str) -> str:
    d = drink.lower().strip()
    if d not in shop.MENU:
        return f"'{drink}' is not a drink name. Use one of: {', '.join(shop.MENU)}."
    return f"{shop.MENU[d]['price']:.2f}"
