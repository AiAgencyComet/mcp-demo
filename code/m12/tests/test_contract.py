"""Contract tests: the tools/list that a model and a client depend on. A snapshot test says THAT the contract changed;
schema_diff says HOW BIG the change is; only the eval says whether the model still picks the right tool."""
import json
from pathlib import Path

import pytest
from mcp import Client

import server
from ship.schema_diff import bump, diff

pytestmark = pytest.mark.anyio
SNAP = Path(__file__).resolve().parents[3] / "data" / "m12" / "versioning"


async def test_tools_list_matches_the_released_snapshot():
    async with Client(server.mcp) as c:
        live = [t.model_dump(by_alias=True, exclude_none=True, mode="json") for t in (await c.list_tools()).tools]
    assert live == json.loads((SNAP / "tools_1.0.0.json").read_text())


def test_a_new_required_field_is_a_major_change():
    old, new = (json.loads((SNAP / f"tools_{v}.json").read_text()) for v in ("1.1.0", "1.2.0-required"))
    levels = {lvl for lvl, _ in diff(old, new)}
    assert "major" in levels and bump("1.1.0", "1.2.0") == "minor"


def test_a_rename_is_remove_plus_add():
    old, new = (json.loads((SNAP / f"tools_{v}.json").read_text()) for v in ("1.1.0", "2.0.0-rc1"))
    assert ("major", "tool removed: place_order") in diff(old, new)


def test_description_only_change_is_not_a_schema_break():
    old, new = (json.loads((SNAP / f"tools_{v}.json").read_text()) for v in ("1.0.0", "1.1.0"))
    assert {lvl for lvl, _ in diff(old, new)} == {"eval"}
