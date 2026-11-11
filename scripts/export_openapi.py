"""Regenerate the REST contract without starting the server or touching a DB."""
import json
import os
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
# Test overrides recreate test.db at app construction; never enable them here.
os.environ['PPAPP_TEST_MODE'] = '0'
from app.main import app

(root / 'openapi.json').write_text(json.dumps(app.openapi(), indent=2) + '\n', encoding='utf-8')
