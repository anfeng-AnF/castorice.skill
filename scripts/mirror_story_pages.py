#!/usr/bin/env python3
"""Mirror story pages locally before parsing."""

from __future__ import annotations

import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent))

from story_parser.mirror import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
