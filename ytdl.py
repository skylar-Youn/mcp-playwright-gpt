#!/usr/bin/env python3
"""Root-level wrapper for the youtube.ytdl CLI."""
from __future__ import annotations

from youtube.ytdl import main


if __name__ == "__main__":
    raise SystemExit(main())
