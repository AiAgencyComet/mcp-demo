#!/usr/bin/env bash
# Four before/after checks. Output -> data/m12/versioning/schema_diff_runs.txt
cd "$(dirname "$0")"; V=../../../data/m12/versioning; PY=../../.venv-new/bin/python
run() { echo "\$ python schema_diff.py tools_$1.json tools_$2.json --old-version $1 --new-version $3"
        $PY schema_diff.py $V/tools_$1.json $V/tools_$2.json --old-version $1 --new-version $3; echo "exit code: $?"; echo; }
run 1.0.0 1.1.0 1.1.0
run 1.1.0 1.2.0-additive 1.2.0
run 1.1.0 1.2.0-required 1.2.0
run 1.1.0 2.0.0-rc1 2.0.0-rc1
