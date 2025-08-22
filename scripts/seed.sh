#!/usr/bin/env bash
set -euo pipefail
BASE_URL=${BASE_URL:-http://127.0.0.1:8000}
echo "Seeding demo tasks to $BASE_URL ..."
curl -sX POST "$BASE_URL/tasks" -H "Content-Type: application/json" -d '{"title":"Draft Today view","tags":["ui","alpha"]}' > /dev/null
curl -sX POST "$BASE_URL/tasks" -H "Content-Type: application/json" -d '{"title":"Implement POST /tasks","tags":["backend","alpha"]}' > /dev/null
curl -sX POST "$BASE_URL/tasks" -H "Content-Type: application/json" -d '{"title":"Write README","tags":["docs","alpha"]}' > /dev/null
echo "Done."
