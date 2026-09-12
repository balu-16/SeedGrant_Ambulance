"""Simple backend runner.

Usage (from the server/ directory, after activating the venv):
    source .venv/bin/activate
    python main.py [--host 0.0.0.0] [--port 8000] [--reload]

Database setup stays manual (migrate + seed explicitly):
    alembic upgrade head
    python -m app.db.seed
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Edge-AI backend (uvicorn).")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()

    import uvicorn

    uvicorn.run("app.main:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
