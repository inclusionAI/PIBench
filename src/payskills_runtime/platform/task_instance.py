import argparse
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence

from payskills_runtime.execution import load_execution_manifest, standard_logs_dir, write_execution_status
from payskills_runtime.result.contract import build_fallback_result, validate_result_contract


@dataclass(frozen=True)
class PlatformTaskInstanceContext:
    task_instance_id: str
    mode: str
    model: str
    timestamp: str
    task_uuid: str
    agent_type: str
    benchmark_suite: str
    suite_version: str
    task_instances_dir: Path
    task_instance_dir: Path
    agent_timeout: int
    repo_root: Path


def repo_root_from_kit() -> Path:
    return Path(__file__).resolve().parents[4]


def run_id() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def parse_case_field(path: Path, field: str, default: str = "") -> str:
    prefix = field + "="
    spaced_prefix = field + " "
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return default
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if not (stripped.startswith(prefix) or stripped.startswith(spaced_prefix)):
            continue
        _, value = stripped.split("=", 1)
        return value.strip().strip("\"'") or default
    return default


def _int_from_text(value: str, default: int) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def default_task_instances_dir(repo_root: Path) -> Path:
    return repo_root / "benchmark_suites" / "default" / "versions" / "v0" / "task_instances"


def parse_platform_task_instance_args(
    argv: Sequence[str],
    *,
    env: Optional[Mapping[str, str]] = None,
    repo_root: Optional[Path] = None,
    default_timestamp: Optional[str] = None,
) -> PlatformTaskInstanceContext:
    parser = argparse.ArgumentParser(prog="payskills-run platform-task-instance")
    parser.add_argument("task_instance_id")
    parser.add_argument("--mode", default="with-skill")
    parser.add_argument("--model", default="")
    parser.add_argument("--timestamp", default="")
    parser.add_argument("--uuid", default="")
    parser.add_argument("--agent-type", default="")
    args = parser.parse_args(list(argv))

    env_map = dict(os.environ if env is None else env)
    root = Path(repo_root or repo_root_from_kit()).resolve()
    task_instances_dir = Path(env_map.get("PAYSKILLS_TASK_INSTANCES_DIR") or default_task_instances_dir(root)).resolve()
    task_instance_dir = task_instances_dir / args.task_instance_id
    case_timeout = _int_from_text(parse_case_field(task_instance_dir / "task_instance.toml", "timeout_sec", "3600"), 3600)
    agent_timeout = _int_from_text(env_map.get("PAYSKILLS_AGENT_TIMEOUT", ""), case_timeout)
    model = args.model or env_map.get("PAYSKILLS_MODEL") or ""
    if not model:
        parser.error("--model or PAYSKILLS_MODEL is required")

    return PlatformTaskInstanceContext(
        task_instance_id=args.task_instance_id,
        mode=args.mode,
        model=model,
        timestamp=args.timestamp or default_timestamp or run_id(),
        task_uuid=args.uuid,
        agent_type=args.agent_type or env_map.get("PAYSKILLS_AGENT_TYPE") or env_map.get("AGENT_TYPE") or "claude-code",
        benchmark_suite=env_map.get("PAYSKILLS_BENCHMARK_SUITE") or "default",
        suite_version=env_map.get("PAYSKILLS_SUITE_VERSION") or "v0",
        task_instances_dir=task_instances_dir,
        task_instance_dir=task_instance_dir,
        agent_timeout=agent_timeout,
        repo_root=root,
    )


def log_dir_for_context(ctx: PlatformTaskInstanceContext) -> Path:
    mode = "oracle" if ctx.mode == "oracle" else ctx.mode
    model = "oracle" if ctx.mode == "oracle" else ctx.model.replace("/", "_")
    return ctx.repo_root / "logs" / "{0}_{1}".format(ctx.timestamp, ctx.task_instance_id) / "{0}_{1}".format(mode, model)


def run_sandbox_task_instance(ctx: PlatformTaskInstanceContext, log_dir: Path, **kwargs: Any) -> Any:
    try:
        from payskills_runtime.platform.sandbox import run_sandbox_task_instance as execute
    except ImportError:
        from payskills_runtime.platform.sandbox import run_sandbox_task_instance as execute

    return execute(ctx, log_dir, **kwargs)


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _validate_or_fallback_result(log_dir: Path) -> Dict[str, Any]:
    log_dir.mkdir(parents=True, exist_ok=True)
    result_path = log_dir / "result.json"
    reason = ""
    payload: Dict[str, Any] = {}

    if not result_path.exists():
        reason = "result.json not produced by evaluation/evaluate.sh"
    else:
        try:
            loaded = json.loads(result_path.read_text(encoding="utf-8", errors="replace"))
            validate_result_contract(loaded)
            payload = loaded
        except Exception as exc:
            validate_message = str(exc)
            logs_dir = standard_logs_dir(log_dir)
            logs_dir.mkdir(parents=True, exist_ok=True)
            (logs_dir / "result_validate.log").write_text(validate_message + "\n", encoding="utf-8")
            reason = "invalid result.json: {0}".format(validate_message.replace("\n", " ")[:300])

    if reason:
        payload = build_fallback_result(reason)
        _write_json(result_path, payload)
    return payload


def _result_reward(result: Mapping[str, Any]) -> Any:
    return result.get("score", 0)


def _result_summary(result: Mapping[str, Any]) -> str:
    summary = result.get("summary", "?/?")
    return summary if isinstance(summary, str) else str(summary)


def write_platform_run_metadata(
    ctx: PlatformTaskInstanceContext,
    log_dir: Path,
    result: Mapping[str, Any],
    *,
    skill_trigger: str = "",
    skill_name: str = "",
    container: str = "",
    sandbox_image: str = "",
    case_layout: str = "task-evaluation",
) -> Dict[str, Any]:
    reward = _result_reward(result)
    metadata = {
        "uuid": ctx.task_uuid,
        "task_instance": ctx.task_instance_id,
        "benchmark_suite": ctx.benchmark_suite,
        "suite_version": ctx.suite_version,
        "task_instances_dir": str(ctx.task_instances_dir),
        "runtime_version": "v2",
        "mode": ctx.mode,
        "model": ctx.model,
        "agent_type": ctx.agent_type,
        "timestamp": ctx.timestamp,
        "reward": reward,
        "evaluation_summary": _result_summary(result),
        "agent_timeout": ctx.agent_timeout,
        "skill_trigger": skill_trigger,
        "skill_name": skill_name,
        "container": container,
        "sandbox_image": sandbox_image,
        "case_layout": case_layout,
    }
    existing = load_execution_manifest(log_dir)
    existing_meta = existing.get("metadata") if isinstance(existing.get("metadata"), dict) else {}
    merged_metadata = dict(existing_meta)
    merged_metadata.update(metadata)
    phases = existing.get("phases") if isinstance(existing.get("phases"), dict) else {}

    def _phase_exit(name: str) -> Optional[int]:
        phase = phases.get(name) if isinstance(phases.get(name), dict) else {}
        value = phase.get("exit_code")
        return int(value) if value is not None else None

    write_execution_status(
        log_dir,
        task_instance={"name": ctx.task_instance_id, "version": ctx.suite_version, "label": ctx.task_instance_id},
        result=result,
        run_exit=_phase_exit("run"),
        diff_exit=_phase_exit("diff"),
        evaluation_exit=_phase_exit("evaluation"),
        metadata=merged_metadata,
    )
    return metadata


def finalize_platform_result_artifacts(
    ctx: PlatformTaskInstanceContext,
    log_dir: Path,
    *,
    skill_trigger: str = "",
    skill_name: str = "",
    container: str = "",
    sandbox_image: str = "",
    case_layout: str = "task-evaluation",
) -> Dict[str, Any]:
    log_path = Path(log_dir)
    result = _validate_or_fallback_result(log_path)
    write_platform_run_metadata(
        ctx,
        log_path,
        result,
        skill_trigger=skill_trigger,
        skill_name=skill_name,
        container=container,
        sandbox_image=sandbox_image,
        case_layout=case_layout,
    )
    return result


def run_platform_task_instance(argv: Sequence[str]) -> int:
    if not argv or argv[0] in {"-h", "--help"}:
        print(
            "usage: payskills-run platform-task-instance <task-instance> --mode <mode> "
            "--model <model> [--timestamp ID] [--uuid ID] [--agent-type TYPE]",
            file=sys.stderr,
        )
        return 2

    ctx = parse_platform_task_instance_args(argv)
    log_dir = log_dir_for_context(ctx)
    try:
        run = run_sandbox_task_instance(ctx, log_dir, env=os.environ)
    except Exception as exc:
        log_dir.mkdir(parents=True, exist_ok=True)
        reason = "platform sandbox failed: {0}".format(str(exc).replace("\n", " ")[:300])
        _write_json(log_dir / "result.json", build_fallback_result(reason))
        finalize_platform_result_artifacts(ctx, log_dir)
        print(reason, file=sys.stderr)
        return 1

    plan = getattr(run, "plan", None)
    if getattr(run, "agent_runtime_ok", True) is False and not (log_dir / "result.json").exists():
        _write_json(log_dir / "result.json", build_fallback_result("agent runtime doctor failed"))
    finalize_platform_result_artifacts(
        ctx,
        log_dir,
        skill_trigger=getattr(plan, "env", {}).get("PAYSKILLS_SKILL_TRIGGER", "") if plan else "",
        skill_name=getattr(plan, "env", {}).get("PAYSKILLS_SKILL_NAME", "") if plan else "",
        container=getattr(plan, "container_name", "") if plan else "",
        sandbox_image=getattr(plan, "sandbox_image", "") if plan else "",
    )
    return 0
