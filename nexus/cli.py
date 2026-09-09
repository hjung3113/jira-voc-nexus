"""Command-line entry point for local dry-run proposals."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, List, Optional

from .errors import NexusError
from .service import process_files


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prepare a local Jira VOC triage proposal")
    parser.add_argument("--event", required=True, help="path to normalized event JSON")
    parser.add_argument("--corpus", required=True, help="path to normalized corpus JSON")
    parser.add_argument("--state", required=True, help="path to local SQLite state")
    parser.add_argument("--engine", choices=("fixture", "opencode"), default="fixture")
    parser.add_argument("--timeout", type=float, default=30.0, help="OpenCode timeout in seconds")
    return parser


def _load_json(path: str) -> Any:
    try:
        with open(path, "r", encoding="utf-8") as stream:
            return json.load(stream)
    except (OSError, ValueError) as exc:
        raise NexusError("input JSON could not be read") from exc


def main(argv: Optional[List[str]] = None) -> int:
    args = _parser().parse_args(argv)
    if args.timeout <= 0:
        print("error: timeout must be positive", file=sys.stderr)
        return 2
    try:
        result = process_files(
            _load_json(args.event),
            _load_json(args.corpus),
            args.state,
            engine=args.engine,
            timeout=args.timeout,
        )
    except NexusError as exc:
        print("error: " + str(exc), file=sys.stderr)
        return 2
    except Exception:
        # Do not expose subprocess, filesystem, or provider details from an
        # unexpected failure at this local CLI boundary.
        print("error: local proposal preparation failed", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0
