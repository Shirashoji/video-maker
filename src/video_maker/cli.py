import argparse
import json
import sys
import time
from pathlib import Path

from .engine import load, render, validate
from .media import doctor, probe, resolve_input
from .service import Service
from .voicevox import Voicevox
from .templates import keynote_template


def wait(service, job_id):
    while True:
        state = service.status(job_id)
        if state["status"] in ("complete", "failed", "interrupted"):
            if state["status"] != "complete":
                raise RuntimeError(state.get("error", state["status"]))
            return state["result"]
        print(state.get("progress", state["status"]), file=sys.stderr, flush=True)
        time.sleep(0.5)


def main():
    parser = argparse.ArgumentParser(description="Local AI video editing")
    parser.add_argument("--workspace", type=Path, default=Path("workspace"))
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor")
    commands.add_parser("speakers")
    commands.add_parser("projects")
    export = commands.add_parser("export-project")
    export.add_argument("project")
    export.add_argument("destination", help="folder or .zip path")
    export.add_argument("--overwrite", action="store_true")
    bundle = commands.add_parser("import-project")
    bundle.add_argument("bundle")
    bundle.add_argument("--path", help="save the project under this workspace path")
    bundle.add_argument("--overwrite", action="store_true")
    template = commands.add_parser("template")
    template.add_argument("--style", choices=["minimal", "colorful"], default="minimal")
    template.add_argument("--title", default="アイデアを、動かそう。")
    template.add_argument("--subtitle", default="映像と図解で、もっと伝わる。")
    template.add_argument("--source")
    for name in ["validate", "plan", "render"]:
        sub = commands.add_parser(name)
        sub.add_argument("project")
        if name == "render":
            sub.add_argument("--preview", action="store_true")
            sub.add_argument("--width", type=int, default=640, help="preview width; never upscales")
            sub.add_argument("--scene", action="append", dest="scenes",
                             help="render only this scene id; repeatable")
    for name in ["inspect", "frames", "frame", "silence"]:
        sub = commands.add_parser(name)
        sub.add_argument("path")
        if name == "frames":
            sub.add_argument("--start", type=float)
            sub.add_argument("--end", type=float)
        if name == "frame":
            sub.add_argument("--time", type=float, required=True, help="timestamp in seconds")
            sub.add_argument("--width", type=int, default=1280, help="never upscales")
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
        elif args.command == "projects":
            result = Service(root).projects()
        elif args.command == "export-project":
            result = Service(root).export_project(args.project, args.destination, args.overwrite)
        elif args.command == "import-project":
            result = Service(root).import_project(args.bundle, args.path, args.overwrite)
        elif args.command == "template":
            result = keynote_template(args.style, args.title, args.subtitle, args.source)
        elif args.command == "validate":
            result = validate(root, load(root, args.project))
        elif args.command == "plan":
            result = Service(root).plan_timeline(args.project)
        elif args.command == "render":
            service = Service(root)
            if args.scenes:
                # Reuse the job path so scene selection behaves exactly as it does over MCP.
                job = service.start(args.project, args.preview, args.scenes, args.width)
                result = wait(service, job["job_id"])
            else:
                result = render(root, args.project, args.preview,
                                lambda p: print(p, file=sys.stderr, flush=True), args.width)
        elif args.command == "inspect":
            result = probe(resolve_input(root, args.path))
        elif args.command == "frames":
            result = Service(root).contact_sheet(args.path, start=args.start, end=args.end)
        elif args.command == "frame":
            result = Service(root).frame(args.path, args.time, args.width)
        else:
            result = Service(root).silence(args.path)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as error:
        print(f"Error: {error}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
