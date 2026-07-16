from typing import Iterable, List


def hint_for_error(error: str) -> str:
    if error.startswith("missing env "):
        env_name = error[len("missing env ") :].strip()
        return (
            "set {0} in config/.env or export it before running ./run.sh; "
            "api_key_env in config/config.yaml should name that variable."
        ).format(env_name)
    if error.startswith("config run.output_dir "):
        return "set run.output_dir to a relative directory such as runs; do not use benchmark_suite/, config/, src/, or absolute paths."
    if error.startswith("config "):
        return "edit config/config.yaml to match the documented types, then rerun ./run.sh --doctor."
    if error.startswith("judge.") or "judge config" in error:
        return "fill judge.base_url, judge.model, and judge.api_key_env together in config/config.yaml."
    if error.startswith("agent.") or error.startswith("unsupported agent."):
        if error.startswith("unsupported agent."):
            return "set agent.type to claude-code, openclaw, or hermes; set agent.mode to no-skill or with-skill."
        return "fill agent.type, agent.model, optional agent.base_url, and agent.api_key_env together in config/config.yaml."
    if error == "docker.image is required when docker.build is false":
        return "set docker.image in config/config.yaml, or change docker.build to true."
    if error == "docker daemon is not reachable":
        return "start Docker, or set docker.enabled to false in config/config.yaml for non-Docker local runs."
    if error == "missing command docker":
        return "install Docker, or set docker.enabled to false in config/config.yaml."
    if error.startswith("missing command ") and " for agent.type " in error:
        return "install the selected agent CLI on PATH, or run with docker.enabled true and an image that contains it."
    if error.startswith("missing command "):
        return "install the required host command, then rerun ./run.sh --doctor."
    if error.startswith("package is incomplete: missing "):
        return "re-export the benchmark suite package or restore the missing top-level package file."
    if error.startswith("package manifest is invalid: "):
        return "re-export the benchmark suite package or restore a valid manifest.json."
    if error.startswith("unsupported manifest "):
        return "re-export the benchmark suite package or restore a valid manifest.json."
    if error.startswith("runtime source is incomplete: missing "):
        return "re-export the benchmark suite package so the vendored src/ directory is complete."
    if error.startswith("configured task instance id is ambiguous: "):
        return "use bare task instance ids in run.task_instances; re-export one version at a time."
    if error.startswith("configured task instance(s) not found: "):
        return "check benchmark_suite/ and run.task_instances in config/config.yaml, then rerun ./run.sh --doctor."
    if error == "no task instances discovered":
        return "check benchmark_suite/ and run.task_instances in config/config.yaml, then rerun ./run.sh --doctor."
    if error.startswith("task instance ") and (
        "task/" in error or "evaluation/" in error or "task_instance.toml" in error or "legacy root" in error
        or "environment/Dockerfile" in error
    ):
        return "add task/Dockerfile, task/run.sh, and evaluation/evaluate.sh to the task instance, or re-export a valid benchmark suite."
    if error.startswith("missing run script for ") or error.startswith("missing evaluation script for "):
        return "add task/Dockerfile, task/run.sh, and evaluation/evaluate.sh to the task instance, or re-export a valid benchmark suite."
    return ""


def hints_for_errors(errors: Iterable[str]) -> List[str]:
    hints = []
    seen = set()
    for error in errors:
        hint = hint_for_error(str(error))
        if hint and hint not in seen:
            hints.append(hint)
            seen.add(hint)
    return hints
