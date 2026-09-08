import argparse
import json
import sys
from pathlib import Path

from .engine import load, render, validate
from .media import doctor, inside, probe
from .service import Service
from .voicevox import Voicevox
from .templates import keynote_template


def main():
    parser = argparse.ArgumentParser(description="Local AI video editing")
    parser.add_argument("--workspace", type=Path, default=Path("workspace"))
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor")
    commands.add_parser("speakers")
    template = commands.add_parser("template")
    template.add_argument("--style", choices=["minimal", "colorful"], default="minimal")
    template.add_argument("--title", default="アイデアを、動かそう。")
    template.add_argument("--subtitle", default="映像と図解で、もっと伝わる。")
    template.add_argument("--source")
    for name in ["validate", "render"]:
        sub = commands.add_parser(name)
        sub.add_argument("project")
        if name == "render":
            sub.add_argument("--preview", action="store_true")
    for name in ["inspect", "frames", "silence"]:
        sub = commands.add_parser(name)
        sub.add_argument("path")
    args = parser.parse_args()
    root = args.workspace.resolve()
    try:
        if args.command == "doctor":
            result = doctor()
            try:
                result["voicevox"] = Voicevox().request("/version").decode()
            except RuntimeError as e:
                result["voicevox_error"] = str(e)
        elif args.command == "speakers":
            result = Voicevox().speakers()
        elif args.command == "template":
            result = keynote_template(args.style, args.title, args.subtitle, args.source)
        elif args.command == "validate":
            result = validate(root, load(root, args.project))
        elif args.command == "render":
            result = render(root, args.project, args.preview, lambda p: print(p, file=sys.stderr, flush=True))
        elif args.command == "inspect":
            result = probe(inside(root, args.path))
        elif args.command == "frames":
            result = Service(root).contact_sheet(args.path)
        else:
            result = Service(root).silence(args.path)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as error:
        print(f"Error: {error}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
