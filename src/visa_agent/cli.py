"""Small argparse CLI. Every command maps directly to one application operation."""

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import sys
import uuid

from .documents import read_document, stage_file
from .replay import replay, run_suite, verify_dataset
from .rules import RULE_VERSION
from .service import VisaService
from .types import CaseEvent, Status


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Inspect and prepare a visa material case")
    parser.add_argument("--data", default=os.getenv("VISA_DATA_DIR", "data"))
    parser.add_argument("--mode", choices=["live", "offline"], default="live")
    sub = parser.add_subparsers(dest="command", required=True)
    new = sub.add_parser("new")
    new.add_argument("case_id")
    for name in ("message", "attach"):
        command = sub.add_parser(name)
        command.add_argument("case_id")
        if name == "message":
            command.add_argument("text")
        else:
            command.add_argument("files", nargs="+")
            command.add_argument("--text", default="")
        command.add_argument("--event-id", default=None)
    for name in ("inspect", "trace", "events"):
        sub.add_parser(name).add_argument("case_id")
    review = sub.add_parser("review")
    review.add_argument("case_id")
    review.add_argument("--version", type=int, required=True)
    review.add_argument("--decision", required=True, choices=["approve", "request_changes", "confirm_fact", "reject_document", "accept_document", "dismiss_event", "refresh"])
    review.add_argument("--notes", required=True)
    review.add_argument("--reviewer", default="local-adviser")
    review.add_argument("--target")
    tick = sub.add_parser("tick")
    tick.add_argument("case_id")
    tick.add_argument("--now", required=True, help="ISO timestamp with timezone")
    tick.add_argument("--event-id", default=None)
    sub.add_parser("read").add_argument("file")
    replayer = sub.add_parser("replay")
    replayer.add_argument("scenario", type=Path)
    replayer.add_argument("--approve-demo", action="store_true")
    suite = sub.add_parser("accept")
    suite.add_argument("--dataset", type=Path, default=Path("datasets"))
    suite.add_argument("--output", type=Path, default=Path("output/acceptance"))
    suite.add_argument("--only", nargs="+")
    verify = sub.add_parser("verify-dataset")
    verify.add_argument("--dataset", type=Path, default=Path("datasets"))
    args = parser.parse_args()
    try:
        service = VisaService(args.data, args.mode)
        if args.command == "new":
            result = service.store.create(args.case_id)
        elif args.command in {"message", "attach", "tick"}:
            data = {"case_id": args.case_id, "event_id": args.event_id or uuid.uuid4().hex,
                    "text": getattr(args, "text", ""), "attachments": getattr(args, "files", []),
                    "kind": "upload" if args.command == "attach" else "tick" if args.command == "tick" else "message"}
            if args.command == "tick":
                data["at"] = datetime.fromisoformat(args.now)
            result = service.handle_event(CaseEvent(**data))
        elif args.command == "inspect":
            result = service.store.get(args.case_id)
            if result.rule_version and result.rule_version != RULE_VERSION:
                result.status = Status.NEEDS_HUMAN
                result.pending_error = "Rules changed; review --decision refresh before using this case"
        elif args.command == "trace":
            result = service.store.traces(args.case_id)
        elif args.command == "events":
            result = service.store.events(args.case_id)
        elif args.command == "review":
            result = service.review_case(args.case_id, args.version, args.decision, args.notes,
                                         reviewer=args.reviewer, target=args.target)
        elif args.command == "read":
            sha, path = stage_file(args.file, service.store.root)
            result = read_document(path, sha, Path(args.file).name)
        elif args.command == "verify-dataset":
            result = {"dataset_hash": verify_dataset(args.dataset), "verified": True}
        elif args.command == "replay":
            result = replay(service, args.scenario, approve_demo=args.approve_demo)
        else:
            result = run_suite(service, args.dataset, args.output, live=args.mode == "live", only=args.only)
        output = result.model_dump(mode="json") if hasattr(result, "model_dump") else result
        print(json.dumps(output, ensure_ascii=False, indent=2, default=str))
        if isinstance(output, dict) and (output.get("error") or output.get("passed") is False):
            raise SystemExit(1)
        if args.command == "accept" and (result["completed"] != len(result["requested"]) or result["passed"] != result["completed"]):
            raise SystemExit(1)
    except (ValueError, FileNotFoundError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(2)


if __name__ == "__main__":
    main()
