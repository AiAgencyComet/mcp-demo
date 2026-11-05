"""Fernhill Coffee: a made-up shop. All data here is invented for the course."""
from datetime import date

MENU = {
    "espresso":   {"price": 3.00, "sizes": ["single", "double"]},
    "latte":      {"price": 4.50, "sizes": ["small", "large"]},
    "flat white": {"price": 4.20, "sizes": ["small"]},
    "cold brew":  {"price": 5.00, "sizes": ["small", "large"]},
    "oat cookie": {"price": 2.50, "sizes": ["one"]},
}
STOCK = {"oat milk": 6, "whole milk": 20, "cold brew": 3, "oat cookie": 12}
ORDERS = {
    "A-1041": {"items": [{"drink": "latte", "size": "large", "milk": "oat"}], "total": 5.10, "status": "done",
               "day": str(date(2026, 11, 4))},
    "A-1042": {"items": [{"drink": "cold brew", "size": "small", "milk": "none"}, {"drink": "oat cookie", "size": "one", "milk": "none"}],
               "total": 7.50, "status": "done", "day": str(date(2026, 11, 4))},
}
REFUND_POLICY = """Fernhill refund policy
1. A refund is possible for 7 days after the order.
2. A refund of more than 20 dollars needs a manager.
3. A refund goes back to the card that paid."""
