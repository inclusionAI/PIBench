import argparse
import json
import os
from pathlib import Path
from typing import List, Optional

from payskills_runtime.agent.doctor import agent_doctor_status
from payskills_runtime.agent.drive import drive_turns
from payskills_runtime.agent.skills import prepare_skills


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="payskills-agent")
    sub = parser.add_subparsers(dest="command")

    prep = sub.add_parser("prepare-skills")
    prep.add_argument("--agent-type", required=True)
    prep.add_argument("--mode", default=os.environ.get("AGENT_MODE", "default"))
    prep.add_argument("--skills", default="/task_instance/skills")
    prep.add_argument("--workspace", default="/workspace")
    prep.add_argument("--home", default=os.environ.get("HOME", "/home/agent"))
    prep.add_argument("--openclaw-profile", default="")

    doctor = sub.add_parser("doctor")
    doctor.add_argument("--output", default="")

    drive = sub.add_parser("drive-turns")
    drive.add_argument("--agent-type", default=os.environ.get("AGENT_TYPE", "claude-code"))
    drive.add_argument("--model", default=os.environ.get("AGENT_MODEL", ""))
    drive.add_argument("--mode", default=os.environ.get("AGENT_MODE", "default"))
    drive.add_argument("--instruction", default="/task_instance/task/instruction.md")
    drive.add_argument("--turns", default="/task_instance/task/turns.json")
    drive.add_argument("--skills", default="/task_instance/skills")
    drive.add_argument("--workspace", default="/workspace")
    drive.add_argument("--output-dir", default=os.environ.get("PAYSKILLS_ARTIFACTS_DIR", "/output/artifacts"))
    drive.add_argument("--task-instance-dir", default="/task_instance")
    drive.add_argument("--case-dir", dest="task_instance_dir", help=argparse.SUPPRESS)
    drive.add_argument("--home", default=os.environ.get("HOME", "/home/agent"))
    drive.add_argument("--timeout", type=int, default=int(os.environ.get("AGENT_TIMEOUT", "600")))
    drive.add_argument("--max-turns", type=int, default=80)
    drive.add_argument("--session-id", default="")
    drive.add_argument("--skill-trigger", choices=["", "slash"], default=os.environ.get("PAYSKILLS_SKILL_TRIGGER", ""))
    drive.add_argument("--skill-name", default=os.environ.get("PAYSKILLS_SKILL_NAME", ""))
    drive.add_argument("--openclaw-profile", default="")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "prepare-skills":
        targets = prepare_skills(
            args.agent_type,
            args.mode,
            args.skills,
            args.workspace,
            args.home,
            openclaw_profile=args.openclaw_profile,
        )
        print(json.dumps({"targets": [str(path) for path in targets]}, ensure_ascii=False))
        return 0
    if args.command == "drive-turns":
        return drive_turns(args)
    if args.command == "doctor":
        status = agent_doctor_status()
        payload = json.dumps(status, ensure_ascii=False, indent=2)
        if args.output:
            Path(args.output).parent.mkdir(parents=True, exist_ok=True)
            Path(args.output).write_text(payload + "\n", encoding="utf-8")
        else:
            print(payload)
        return 0 if status["ok"] else 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
