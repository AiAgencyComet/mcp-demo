from mcp.server import MCPServer

mcp = MCPServer("fernhill")

@mcp.tool()
def get_price(drink: str) -> str:
    """Return the price of one drink at Fernhill Coffee, in US dollars."""
    menu = {"latte": "4.50", "flat white": "4.20", "cold brew": "5.00"}
    return menu.get(drink.lower(), f"{drink} is not on the menu. Drinks: {', '.join(menu)}.")

mcp.run()
