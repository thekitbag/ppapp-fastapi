import os
import sys

# Enable application test-mode overrides (isolated DB + auth bypass)
os.environ.setdefault("PPAPP_TEST_MODE", "1")

# Ensure project root is on sys.path so `import app` works in all environments
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
