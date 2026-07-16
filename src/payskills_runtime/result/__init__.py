import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from payskills_runtime.result.contract import build_fallback_result, validate_result_contract
from payskills_runtime.result.scoring import compose_result


def _read_json(path: str) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _read_agent_usage(path: str) -> Dict[str, Any]:
    if not path:
        return {"usage_available": False}
    try:
        payload = _read_json(path)
    except Exception:
        return {"usage_available": False}
    return payload if isinstance(payload, dict) else {"usage_available": False}


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="payskills-result")
    sub = parser.add_subparsers(dest="command")
    validate = sub.add_parser("validate")
    validate.add_argument("--input", default="/output/result.json")
    fallback = sub.add_parser("fallback")
    fallback.add_argument("--output", default="/output/result.json")
    fallback.add_argument("--reason", required=True)
    compose = sub.add_parser("compose")
    compose.add_argument("--rubric-file", required=True)
    compose.add_argument("--input", action="append", default=[])
    compose.add_argument("--agent-file", default="/output/artifacts/agent_usage.json")
    compose.add_argument("--metadata-file", default="")
    compose.add_argument("--output", default="/output/result.json")
    args = parser.parse_args(argv)

    if args.command == "validate":
        payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
        validate_result_contract(payload)
        return 0
    if args.command == "fallback":
        payload = build_fallback_result(args.reason)
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return 0
    if args.command == "compose":
        rubric_defs = _read_json(args.rubric_file)
        inputs = [_read_json(path) for path in args.input]
        metadata = None
        if args.metadata_file:
            metadata_payload = _read_json(args.metadata_file)
            if isinstance(metadata_payload, dict) and isinstance(metadata_payload.get("metadata"), dict):
                metadata = metadata_payload["metadata"]
        payload = compose_result(
            rubric_defs,
            inputs,
            agent=_read_agent_usage(args.agent_file),
            metadata=metadata,
        )
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
