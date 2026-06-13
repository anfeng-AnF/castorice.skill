#!/usr/bin/env python3
"""Compatibility wrapper for the story_parser framework."""

from __future__ import annotations

import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent))

from story_parser.cli import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
