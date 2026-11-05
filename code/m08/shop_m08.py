"""Fernhill Coffee data for module 8. Copied from code/fernhill/shop.py (all data invented),
plus five open orders for today so the order board has something to show."""

MENU = {
    "espresso":   {"price": 3.00, "sizes": ["single", "double"]},
    "latte":      {"price": 4.50, "sizes": ["small", "large"]},
    "flat white": {"price": 4.20, "sizes": ["small"]},
    "cold brew":  {"price": 5.00, "sizes": ["small", "large"]},
    "oat cookie": {"price": 2.50, "sizes": ["one"]},
}

# status: "making" -> "ready" -> "done"
ORDERS = {
    "A-1041": {"name": "Priya",  "items": ["latte large, oat"],                 "total": 5.10, "status": "done",   "placed": "08:02"},
    "A-1042": {"name": "Tom",    "items": ["cold brew small", "oat cookie"],    "total": 7.50, "status": "done",   "placed": "08:09"},
    "A-1043": {"name": "Mara",   "items": ["flat white small"],                 "total": 4.20, "status": "ready",  "placed": "08:14"},
    "A-1044": {"name": "Jonas",  "items": ["espresso double", "oat cookie"],    "total": 5.50, "status": "ready",  "placed": "08:17"},
    "A-1045": {"name": "Ines",   "items": ["latte small, oat"],                 "total": 5.10, "status": "making", "placed": "08:21"},
    "A-1046": {"name": "Sam",    "items": ["cold brew large"],                  "total": 5.00, "status": "making", "placed": "08:23"},
    "A-1047": {"name": "Leo",    "items": ["latte large", "espresso single"],   "total": 7.50, "status": "making", "placed": "08:26"},
}
