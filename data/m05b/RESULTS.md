# Module 5b · error recovery (measured 2026-11-05, claude-haiku-5-5, 10 runs per cell, data/m05b/recovery.jsonl)
Same Fernhill server; only the exception type changes. ValueError = the SDK hides the text ("Error executing tool place_order");
ToolError = the model reads "Error executing tool place_order: cold brew is sold out today. Offer a latte or a flat white instead."
Score = the final answer names the real cause (regex per case).

| case (can the model check first?) | hidden error | ToolError hint | avg tool calls hidden / hint |
|---|---|---|---|
| sold out today (no) | 0/10 | 10/10 | 2.5 / 2.0 |
| refund of A-9999 (no) | 0/10 | 9/10 | 1.5 / 1.0 |
| status of B-2001 (no) | 0/10 | 10/10 | 2.0 / 1.0 |
| large flat white (yes, get_menu shows sizes) | 10/10 | 10/10 | 1.0 / 1.0 |
| mocha (yes, get_menu shows the menu) | 9/10 | 10/10 | 1.0 / 1.0 |
Errors the model cannot foresee: hidden 0/30, hint 29/30. When a tool lets the model look first, it looks first (get_menu) and never hits the error.
Hidden answer (verbatim): "I couldn't place the order. The system returned an error, and I don't have a confirmed order ID."
Hint answer (verbatim): "The large cold brew is sold out today, so I haven't placed the order. Would you like a different drink ..."
