"""Tool-choice eval cases for Fernhill. Written by hand as a shop manager talks (short, vague, no tool words).
Labels use the v1 tool names. `expect` is checked against the real server after the call runs."""

# Other servers that the same host has connected. Good definitions, written by other teams.
DISTRACTORS = [
    {"name": "stock__check_stock",
     "description": "Return how many units of one stock item are left in the back room, for example oat milk cartons, coffee beans or cups.",
     "input_schema": {"type": "object", "properties": {"item": {"type": "string", "description": "Stock item name"}}, "required": ["item"]}},
    {"name": "suppliers__create_purchase_order",
     "description": "Create a purchase order to buy stock from a supplier.",
     "input_schema": {"type": "object", "properties": {
         "supplier": {"type": "string"}, "item": {"type": "string"},
         "quantity": {"type": "integer", "minimum": 1}}, "required": ["supplier", "item", "quantity"]}},
    {"name": "staff__list_shifts",
     "description": "List the staff shifts for one day.",
     "input_schema": {"type": "object", "properties": {"day": {"type": "string", "description": "A day name or a date"}}, "required": ["day"]}},
    {"name": "loyalty__get_points",
     "description": "Return the loyalty points balance of one customer.",
     "input_schema": {"type": "object", "properties": {"customer_name": {"type": "string"}}, "required": ["customer_name"]}},
    {"name": "catering__quote_event",
     "description": "Make a price quote for a catering event: coffee for a group, delivered to an office or an event.",
     "input_schema": {"type": "object", "properties": {
         "people": {"type": "integer"}, "day": {"type": "string"}, "address": {"type": "string"}}, "required": ["people", "day"]}},
]

def pickup(name): return {"kind": "pickup", "name": name}
def delivery(addr): return {"kind": "delivery", "address_has": addr}
def item(drink, size, milk=None):
    return {"drink": drink, "size": size, **({"milk": milk} if milk else {})}

CASES = [
    # --- get_menu (7) ---
    ("menu-01", "What do we charge for a flat white these days?", "get_menu", None),
    ("menu-02", "A customer wants to know what sizes the cold brew comes in.", "get_menu", None),
    ("menu-03", "Pull up the full drinks list with prices, I'm redoing the chalkboard.", "get_menu", None),
    ("menu-04", "Is there anything on the menu under three dollars?", "get_menu", None),
    ("menu-05", "Someone asked if we do a large flat white. Do we?", "get_menu", None),
    ("menu-06", "Read me the menu.", "get_menu", None),
    ("menu-07", "How much is an oat cookie?", "get_menu", None),
    # --- place_order (10) ---
    ("order-01", "Ring up a large oat latte for pickup, name's Sam.", "place_order",
     {"items": [item("latte", "large", "oat")], "handoff": pickup("Sam")}),
    ("order-02", "Two small cold brews to go for Priya.", "place_order",
     {"items": [item("cold brew", "small"), item("cold brew", "small")], "handoff": pickup("Priya")}),
    ("order-03", "Put in a double espresso for Jordan, they'll grab it at the counter.", "place_order",
     {"items": [item("espresso", "double")], "handoff": pickup("Jordan")}),
    ("order-04", "Delivery to 12 Elm Street: one large latte, whole milk.", "place_order",
     {"items": [item("latte", "large", "whole")], "handoff": delivery("12 Elm")}),
    ("order-05", "An oat cookie and a single espresso for pickup under the name Lee.", "place_order",
     {"items": [item("oat cookie", "one"), item("espresso", "single")], "handoff": pickup("Lee")}),
    ("order-06", "New order: small flat white with oat milk, collect at the counter, name Maya.", "place_order",
     {"items": [item("flat white", "small", "oat")], "handoff": pickup("Maya")}),
    ("order-07", "Can you send a large cold brew to 4 Harbour Road?", "place_order",
     {"items": [item("cold brew", "large")], "handoff": delivery("4 Harbour")}),
    ("order-08", "Start an order for Ana, a small latte with whole milk, she's picking it up.", "place_order",
     {"items": [item("latte", "small", "whole")], "handoff": pickup("Ana")}),
    ("order-09", "Chris at the window wants a large latte and an oat cookie. Pickup.", "place_order",
     {"items": [item("latte", "large"), item("oat cookie", "one")], "handoff": pickup("Chris")}),
    ("order-10", "Add a single espresso for pickup, name Kim.", "place_order",
     {"items": [item("espresso", "single")], "handoff": pickup("Kim")}),
    # --- order_status (7) ---
    ("status-01", "Is A-1042 ready yet?", "order_status", {"order_id": "A-1042"}),
    ("status-02", "The guy at the counter says he's been waiting ages. Order A-1041, where is it?", "order_status", {"order_id": "A-1041"}),
    ("status-03", "Check on order A-1042 for me.", "order_status", {"order_id": "A-1042"}),
    ("status-04", "What's going on with A-1041?", "order_status", {"order_id": "A-1041"}),
    ("status-05", "Has A-1042 gone out?", "order_status", {"order_id": "A-1042"}),
    ("status-06", "Customer asking whether their order A-1041 is done.", "order_status", {"order_id": "A-1041"}),
    ("status-07", "How much was order A-1042?", "order_status", {"order_id": "A-1042"}),
    # --- refund (6) ---
    ("refund-01", "Refund A-1042, the cold brew was warm.", "refund", {"order_id": "A-1042"}),
    ("refund-02", "The customer on A-1041 wants their money back.", "refund", {"order_id": "A-1041"}),
    ("refund-03", "Give the money back for order A-1042.", "refund", {"order_id": "A-1042"}),
    ("refund-04", "We got A-1041 wrong. Please reverse the charge.", "refund", {"order_id": "A-1041"}),
    ("refund-05", "We messed up A-1042. Refund it.", "refund", {"order_id": "A-1042"}),
    ("refund-06", "Please process a refund for order A-1041.", "refund", {"order_id": "A-1041"}),
    # --- requests for the OTHER servers (6): Fernhill must not grab these ---
    ("other-01", "How many oat milk cartons are left in the back?", "stock__check_stock", None),
    ("other-02", "Order 20 cartons of oat milk from Green Valley Dairy.", "suppliers__create_purchase_order", None),
    ("other-03", "We're low on cold brew concentrate. Reorder 10 from Riverside Roasters.", "suppliers__create_purchase_order", None),
    ("other-04", "Who's working on Saturday?", "staff__list_shifts", None),
    ("other-05", "How many loyalty points does Priya have?", "loyalty__get_points", None),
    ("other-06", "An office wants coffee for 40 people on Friday. Get me a quote.", "catering__quote_event", None),
]
assert len(CASES) == 36 and len({c[0] for c in CASES}) == 36

# Holdout set: written AFTER the v1 run showed its failures and BEFORE any v1.1 run.
# Used only to check the v1.1 fix fairly (the fix was designed while looking at CASES).
HOLDOUT = [
    ("menu-h1", "What's the cheapest drink we sell?", "get_menu", None),
    ("menu-h2", "Does the latte come in a small?", "get_menu", None),
    ("order-h1", "One Flat White, Small, oat milk, for pickup. Name is Theo.", "place_order",
     {"items": [item("flat white", "small", "oat")], "handoff": pickup("Theo")}),
    ("order-h2", "Ring up an Oat Cookie and a Small Latte for Dana, pickup.", "place_order",
     {"items": [item("oat cookie", "one"), item("latte", "small")], "handoff": pickup("Dana")}),
    ("order-h3", "Send two large lattes with oat milk to 9 Mill Lane.", "place_order",
     {"items": [item("latte", "large", "oat"), item("latte", "large", "oat")], "handoff": delivery("9 Mill")}),
    ("order-h4", "A double espresso and a cookie for Omar, he's waiting at the counter.", "place_order",
     {"items": [item("espresso", "double"), item("oat cookie", "one")], "handoff": pickup("Omar")}),
    ("status-h1", "Where are we with A-1041?", "order_status", {"order_id": "A-1041"}),
    ("status-h2", "Did A-1042 get finished?", "order_status", {"order_id": "A-1042"}),
    ("refund-h1", "A-1041: the customer says it was the wrong milk and wants a refund.", "refund", {"order_id": "A-1041"}),
    ("refund-h2", "Money back on A-1042 please.", "refund", {"order_id": "A-1042"}),
    ("other-h1", "Do we have enough cups for the weekend?", "stock__check_stock", None),
    ("other-h2", "Get me a price for a coffee cart at a wedding, 120 guests, Sunday.", "catering__quote_event", None),
]
assert len(HOLDOUT) == 12 and not {c[0] for c in HOLDOUT} & {c[0] for c in CASES}
