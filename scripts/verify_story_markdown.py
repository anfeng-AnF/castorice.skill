from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional, Sequence

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from story_parser.coverage import (
        verify_story_markdown,
        write_json_report,
        write_markdown_report,
    )
else:
    from .story_parser.coverage import (
        verify_story_markdown,
        write_json_report,
        write_markdown_report,
    )


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "sources" / "extracted" / "coverage_report.md"


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify that a generated story Markdown keeps text from a mirrored BWiki HTML page."
    )
    parser.add_argument("--html", type=Path, required=True, help="Mirrored local HTML file.")
    parser.add_argument("--markdown", type=Path, required=True, help="Generated story Markdown file.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help=f"Markdown report path. Default: {DEFAULT_OUTPUT}")
    parser.add_argument("--json-output", type=Path, help="Optional JSON report path.")
    parser.add_argument("--max-items", type=int, default=80, help="Maximum missing/extra examples to write.")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    report = verify_story_markdown(args.html, args.markdown, max_items=args.max_items)
    write_markdown_report(args.output, report)
    print(f"Wrote {args.output}", file=sys.stderr)

    if args.json_output:
        write_json_report(args.json_output, report)
        print(f"Wrote {args.json_output}", file=sys.stderr)

    print(f"status={report.status}", file=sys.stderr)
    for key, value in report.counts.items():
        print(f"{key}={value}", file=sys.stderr)

    return 0 if report.status in {"pass", "warn"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
