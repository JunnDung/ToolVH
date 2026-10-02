from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .model import Project


def main():
    # Windows consoles/pipes may default to a code page without Vietnamese.
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="ToolVH — quét và Việt hóa text game")
    sub = parser.add_subparsers(dest="command")
    gui = sub.add_parser("gui")
    gui.add_argument("--project")
    gui.add_argument("--smoke-report", help=argparse.SUPPRESS)
    scan = sub.add_parser("scan")
    scan.add_argument("game")
    scan.add_argument("--out", required=True)
    scan.add_argument("--deep", action="store_true")
    scan.add_argument("--max-mb", type=int, default=256)
    for name in ("export-csv", "import-csv", "patch"):
        command = sub.add_parser(name)
        command.add_argument("project")
        command.add_argument("path")
    check = sub.add_parser("check")
    check.add_argument("project")
    translation = sub.add_parser("translate")
    translation.add_argument("project")
    from .translation import PROVIDERS
    translation.add_argument("--provider", choices=list(PROVIDERS), default="gemini")
    translation.add_argument("--base-url")
    translation.add_argument("--model", default="")
    translation.add_argument("--batch-size", type=int, default=20)
    translation.add_argument("--delay", type=int, default=2)
    for name in ("apply", "restore"):
        command = sub.add_parser(name)
        command.add_argument("patch")
        command.add_argument("game")
    args = parser.parse_args()
    try:
        if args.command in (None, "gui"):
            smoke_report = getattr(args, "smoke_report", None)
            if smoke_report:
                os.environ["QT_QPA_PLATFORM"] = "offscreen"
            from .gui import run
            return run(getattr(args, "project", None), smoke_report=smoke_report)
        if args.command == "scan":
            from .scanner import scan as scan_game
            project = scan_game(args.game, print, deep=args.deep, max_mb=args.max_mb)
            project.save(args.out)
            print(f"Saved {args.out}: {len(project.entries)} entries")
        elif args.command == "check":
            from .patching import preflight
            import json
            print(json.dumps(preflight(Project.load(args.project), print), ensure_ascii=False, indent=2))
        elif args.command == "translate":
            from .translation import APIConfig, PROVIDERS, translate, environment_key
            project = Project.load(args.project)
            from .patching import preflight
            preflight(project, print)
            key = environment_key(args.provider)
            config = APIConfig(args.provider, args.base_url or PROVIDERS[args.provider][1], args.model, key, args.batch_size, delay_seconds=args.delay)
            translate(project, config, print, save=lambda: project.save(args.project))
        else:
            from .patching import export_csv, export_patch, import_csv, install_patch
            if args.command in ("apply", "restore"):
                print(install_patch(args.patch, args.game, args.command == "restore"), "file(s)")
            else:
                project = Project.load(args.project)
                if args.command == "export-csv":
                    export_csv(project, args.path)
                elif args.command == "import-csv":
                    print(import_csv(project, args.path), "entries imported")
                    project.save(args.project)
                elif args.command == "patch":
                    print(export_patch(project, args.path, print))
        return 0
    except Exception as exc:
        parser.exit(1, f"ToolVH: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
