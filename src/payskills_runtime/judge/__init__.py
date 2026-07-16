import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from urllib.error import HTTPError
except ImportError:  # pragma: no cover - Python 2 fallback is harmless.
    from urllib2 import HTTPError

from payskills_runtime.judge.transport import call_judge, extract_json_object, response_text


FIXED_JUDGE_TIMEOUT_SECONDS = 1200
DEFAULT_JUDGE_MAX_TOKENS = 12000


def _read_prompt(args: argparse.Namespace) -> str:
    if args.prompt:
        return args.prompt
    if args.prompt_file:
        return Path(args.prompt_file).read_text(encoding="utf-8", errors="replace")
    return sys.stdin.read()


def _error_summary(exc: Exception) -> str:
    if isinstance(exc, HTTPError):
        reason = getattr(exc, "reason", "") or ""
        return "HTTP {0} {1}".format(exc.code, reason).strip()
    return str(exc) or repr(exc)


def _is_retryable_error(exc: Exception) -> bool:
    if isinstance(exc, HTTPError):
        return exc.code not in {401, 403, 404}
    return True


def _retry_delay(backoff: str, retry_index: int) -> float:
    value = str(backoff or "0").strip()
    if not value:
        return 0.0
    parts = [part.strip() for part in value.split(",") if part.strip()]
    if not parts:
        return 0.0
    try:
        delays = [max(0.0, float(part)) for part in parts]
    except ValueError:
        return 0.0
    if "," in value:
        return delays[min(retry_index - 1, len(delays) - 1)]
    return delays[0] * (2 ** max(0, retry_index - 1))


def _evaluate_once(prompt: str, args: argparse.Namespace) -> Dict[str, Any]:
    response = call_judge(
        prompt,
        model=args.model,
        base_url=args.base_url,
        api_key=args.api_key,
        max_tokens=args.max_tokens,
        timeout=FIXED_JUDGE_TIMEOUT_SECONDS,
    )
    text = response_text(response)
    if args.raw_text:
        return {"text": text, "raw_response": response}
    return json.loads(extract_json_object(text))


def _evaluate_with_retries(prompt: str, args: argparse.Namespace) -> Optional[Dict[str, Any]]:
    retries = max(0, int(args.retries))
    max_attempts = retries + 1
    errors = []
    for attempt in range(1, max_attempts + 1):
        try:
            return _evaluate_once(prompt, args)
        except Exception as exc:
            retryable = _is_retryable_error(exc)
            summary = "{0}: {1}".format(type(exc).__name__, _error_summary(exc))
            errors.append(summary)
            print(
                "payskills-judge attempt {0}/{1} failed: {2}".format(
                    attempt, max_attempts, summary
                ),
                file=sys.stderr,
            )
            if not retryable:
                print("payskills-judge failure is non-retryable; aborting.", file=sys.stderr)
                return None
            if attempt >= max_attempts:
                break
            delay = _retry_delay(args.retry_backoff, attempt)
            print(
                "payskills-judge retrying after {0:.2f}s".format(delay),
                file=sys.stderr,
            )
            if delay:
                time.sleep(delay)
    print("payskills-judge exhausted retries. errors: " + " | ".join(errors), file=sys.stderr)
    return None


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="payskills-judge")
    sub = parser.add_subparsers(dest="command")
    eval_cmd = sub.add_parser("eval")
    eval_cmd.add_argument("--prompt-file", default="")
    eval_cmd.add_argument("--prompt", default="")
    eval_cmd.add_argument("--output", default="/output/judge_result.json")
    eval_cmd.add_argument("--model", default=os.environ.get("RUBRIC_MODEL", ""))
    eval_cmd.add_argument("--base-url", default=os.environ.get("RUBRIC_BASE_URL") or os.environ.get("ANTHROPIC_BASE_URL", ""))
    eval_cmd.add_argument("--api-key", default=os.environ.get("RUBRIC_API_KEY") or os.environ.get("ANTHROPIC_API_KEY", ""))
    eval_cmd.add_argument("--max-tokens", dest="case_max_tokens", default="", help=argparse.SUPPRESS)
    eval_cmd.add_argument("--timeout", type=int, default=FIXED_JUDGE_TIMEOUT_SECONDS, help=argparse.SUPPRESS)
    eval_cmd.add_argument("--retries", type=int, default=int(os.environ.get("RUBRIC_RETRIES", "3")))
    eval_cmd.add_argument("--retry-backoff", default=os.environ.get("RUBRIC_RETRY_BACKOFF", "1"))
    eval_cmd.add_argument("--raw-text", action="store_true", help="Write judge text instead of extracting JSON")
    args = parser.parse_args(argv)

    if args.command != "eval":
        parser.print_help()
        return 2
    missing = []
    if not str(args.model).strip():
        missing.append("--model or RUBRIC_MODEL")
    if not str(args.base_url).strip():
        missing.append("--base-url or RUBRIC_BASE_URL")
    if not str(args.api_key).strip():
        missing.append("--api-key or RUBRIC_API_KEY")
    if missing:
        print(
            "payskills-judge: missing required configuration: " + ", ".join(missing),
            file=sys.stderr,
        )
        return 2
    if args.case_max_tokens:
        print(
            "payskills-judge: cases must not configure payskills-judge --max-tokens; "
            "the platform/kit controls RUBRIC_MAX_TOKENS.",
            file=sys.stderr,
        )
        return 2
    args.max_tokens = int(os.environ.get("RUBRIC_MAX_TOKENS", str(DEFAULT_JUDGE_MAX_TOKENS)))

    prompt = _read_prompt(args)
    output = _evaluate_with_retries(prompt, args)
    if output is None:
        return 1

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
