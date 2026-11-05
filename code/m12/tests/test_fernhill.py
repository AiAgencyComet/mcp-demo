"""Unit tests for the Fernhill MCP server. In-process client: no network, no model, about 1 s for the file."""
import sys

import mcp_types as types
import pytest
from mcp import Client, StdioServerParameters
from mcp.shared.exceptions import MCPError

import server  # code/fernhill/server.py

pytestmark = pytest.mark.anyio


async def say_yes(ctx, params):
    """The person in the host clicks 'confirm'."""
    return types.ElicitResult(action="accept", content={"confirm": True})


async def say_no(ctx, params):
    return types.ElicitResult(action="decline")


# ---------- tools/list: the contract that the model reads ----------

async def test_tools_list_names():
    async with Client(server.mcp) as c:
        tools = (await c.list_tools()).tools
    assert [t.name for t in tools] == ["get_menu", "place_order", "order_status", "refund"]


async def test_every_tool_has_a_real_description():
    async with Client(server.mcp) as c:
        tools = (await c.list_tools()).tools
    for t in tools:
        assert t.description and len(t.description.split()) >= 4, t.name


async def test_place_order_schema():
    async with Client(server.mcp) as c:
        po = next(t for t in (await c.list_tools()).tools if t.name == "place_order")
    s = po.input_schema
    assert s["type"] == "object"
    assert set(s["required"]) == {"items", "handoff"}
    assert [b["$ref"] for b in s["properties"]["handoff"]["anyOf"]] == ["#/$defs/Pickup", "#/$defs/Delivery"]
    assert s["$defs"]["Item"]["properties"]["milk"]["enum"] == ["whole", "oat", "none"]
    assert po.output_schema["required"] == ["order_id", "total", "status"]


async def test_refund_hides_the_confirm_parameter():
    """`answer` is filled by the server (Resolve + Elicit). The model must not see it."""
    async with Client(server.mcp) as c:
        rf = next(t for t in (await c.list_tools()).tools if t.name == "refund")
    assert list(rf.input_schema["properties"]) == ["order_id"]


# ---------- tools/call: good input ----------

async def test_get_menu():
    async with Client(server.mcp) as c:
        r = await c.call_tool("get_menu", {})
    assert not r.is_error
    drinks = {m["drink"]: m["price"] for m in r.structured_content["result"]}
    assert drinks["latte"] == 4.50 and len(drinks) == 5


async def test_good_order():
    async with Client(server.mcp) as c:
        r = await c.call_tool("place_order", {"items": [{"drink": "latte", "size": "large", "milk": "oat"}],
                                              "handoff": {"kind": "pickup", "name": "Sam"}})
    assert not r.is_error
    assert r.structured_content == {"order_id": "A-1043", "total": 5.10, "status": "making"}


async def test_order_then_status():
    async with Client(server.mcp) as c:
        r = await c.call_tool("place_order", {"items": [{"drink": "espresso", "size": "double"}],
                                              "handoff": {"kind": "delivery", "address": "12 Elm Street"}})
        s = await c.call_tool("order_status", {"order_id": r.structured_content["order_id"]})
    assert s.structured_content["status"] == "making" and s.structured_content["total"] == 3.00


# ---------- tools/call: bad input gives an error that the model can use ----------

async def test_bad_drink_is_a_tool_error_with_a_hint():
    async with Client(server.mcp) as c:
        r = await c.call_tool("place_order", {"items": [{"drink": "mocha", "size": "large"}],
                                              "handoff": {"kind": "pickup", "name": "Sam"}})
    assert r.is_error
    assert r.content[0].text == ("Error executing tool place_order: "
                                 "'mocha' is not on the menu. Call get_menu to see the menu.")


async def test_bad_size_lists_the_good_sizes():
    async with Client(server.mcp) as c:
        r = await c.call_tool("place_order", {"items": [{"drink": "flat white", "size": "large"}],
                                              "handoff": {"kind": "pickup", "name": "Sam"}})
    assert r.is_error and "Sizes: ['small']" in r.content[0].text


async def test_schema_violation_is_an_error_result_not_an_exception():
    async with Client(server.mcp) as c:
        r = await c.call_tool("place_order", {"items": [{"drink": "latte"}], "handoff": {"kind": "pickup", "name": "Sam"}})
    assert r.is_error and "items.0.size" in r.content[0].text


async def test_unknown_order():
    async with Client(server.mcp) as c:
        r = await c.call_tool("order_status", {"order_id": "Z-1"})
    assert r.is_error and "Order IDs look like A-1041" in r.content[0].text


# ---------- the confirm step (elicitation) ----------

async def test_refund_when_the_person_confirms():
    async with Client(server.mcp, elicitation_callback=say_yes) as c:
        r = await c.call_tool("refund", {"order_id": "A-1042"})
        s = await c.call_tool("order_status", {"order_id": "A-1042"})
    assert r.structured_content == {"result": "Refunded $7.50 for A-1042."}
    assert s.structured_content["status"] == "refunded"


async def test_refund_when_the_person_declines():
    async with Client(server.mcp, elicitation_callback=say_no) as c:
        r = await c.call_tool("refund", {"order_id": "A-1042"})
        s = await c.call_tool("order_status", {"order_id": "A-1042"})
    assert r.structured_content == {"result": "The person stopped the refund."}
    assert s.structured_content["status"] == "done"


async def test_refund_is_refused_for_a_client_that_cannot_ask_a_person():
    async with Client(server.mcp) as c:            # no elicitation_callback -> no elicitation capability
        with pytest.raises(MCPError, match="did not declare the form elicitation capability"):
            await c.call_tool("refund", {"order_id": "A-1042"})


# ---------- resources and prompts ----------

async def test_resources_and_template():
    async with Client(server.mcp) as c:
        res = await c.list_resources()
        tmpl = await c.list_resource_templates()
        pol = await c.read_resource("fernhill://policy/refunds")
        one = await c.read_resource("fernhill://orders/A-1041")
    assert sorted(str(r.uri) for r in res.resources) == ["fernhill://menu", "fernhill://policy/refunds"]
    assert [t.uri_template for t in tmpl.resource_templates] == ["fernhill://orders/{order_id}"]
    assert "more than 20 dollars needs a manager" in pol.contents[0].text
    assert '"total": 5.1' in one.contents[0].text


async def test_missing_order_resource_raises():
    async with Client(server.mcp) as c:
        with pytest.raises(MCPError, match="Error creating resource from template"):
            await c.read_resource("fernhill://orders/Z-9")


async def test_prompts():
    async with Client(server.mcp) as c:
        names = [p.name for p in (await c.list_prompts()).prompts]
        pr = await c.get_prompt("complaint_reply", {"order_id": "A-1042", "complaint": "The cold brew was warm."})
    assert names == ["daily_report", "complaint_reply"]
    text = pr.messages[0].content.text
    assert "order A-1042" in text and "fernhill://policy/refunds" in text


# ---------- smoke test: start the server the way a host starts it (stdio subprocess) ----------

async def test_stdio_smoke():
    params = StdioServerParameters(command=sys.executable, args=[server.__file__])
    async with Client(params) as c:
        tools = (await c.list_tools()).tools
        r = await c.call_tool("order_status", {"order_id": "A-1041"})
    assert len(tools) == 4 and r.structured_content["status"] == "done"
