"""The unit tests that ship with the v2.0.0-rc1 refactor PR. They were updated for the new names, and they pass.
They test the code. They cannot test whether a model still picks the right tool."""
import mcp_types as types
import pytest
from mcp import Client

from releases import fernhill_v2_bad as v2

pytestmark = pytest.mark.anyio


async def say_yes(ctx, params):
    return types.ElicitResult(action="accept", content={"confirm": True})


async def test_v2_tools_list():
    async with Client(v2.mcp) as c:
        assert [t.name for t in (await c.list_tools()).tools] == ["mn_list", "po_create", "po_get", "po_refund"]


async def test_v2_good_order():
    async with Client(v2.mcp) as c:
        r = await c.call_tool("po_create", {"p1": [{"drink": "latte", "size": "large", "milk": "oat"}],
                                            "p2": {"kind": "pickup", "name": "Sam"}})
    assert r.structured_content == {"order_id": "A-1043", "total": 5.10, "status": "making"}


async def test_v2_bad_drink():
    async with Client(v2.mcp) as c:
        r = await c.call_tool("po_create", {"p1": [{"drink": "mocha", "size": "large"}], "p2": {"kind": "pickup", "name": "Sam"}})
    assert r.is_error and "not on the menu" in r.content[0].text


async def test_v2_status_and_refund():
    async with Client(v2.mcp, elicitation_callback=say_yes) as c:
        r = await c.call_tool("po_refund", {"p1": "A-1042"})
        s = await c.call_tool("po_get", {"p1": "A-1042"})
    assert r.structured_content == {"result": "Refunded $7.50 for A-1042."} and s.structured_content["status"] == "refunded"
