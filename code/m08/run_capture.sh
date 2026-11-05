#!/bin/zsh
# Start the module 8 MCP server and the local test host on 127.0.0.1, run the Playwright capture,
# then stop both servers. Usage: ./run_capture.sh [capture.py | checks.py]
set -u
HERE=${0:A:h}
PY=$HERE/../.venv-new/bin/python
DATA=$HERE/../../data/m08
mkdir -p $DATA

cd $HERE
$PY server.py http 8810 > $DATA/server_http.log 2>&1 &
SERVER=$!
$PY host/host_server.py http://127.0.0.1:8810/mcp > $DATA/host_server.log 2>&1 &
HOSTP=$!
trap 'kill $SERVER $HOSTP 2>/dev/null; wait $SERVER $HOSTP 2>/dev/null' EXIT

for i in {1..50}; do
  curl -s -o /dev/null http://127.0.0.1:8810/mcp && curl -s -o /dev/null http://127.0.0.1:8820/ && break
  sleep 0.2
done

SCRIPT=${1:-capture.py}
$PY $SCRIPT
