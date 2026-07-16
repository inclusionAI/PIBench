from typing import Dict, List

from payskills_runtime.execution.run_paths import output_dir_errors


def _is_positive_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _is_bool(value) -> bool:
    return isinstance(value, bool)


def _string_field_errors(section_name: str, section: Dict, fields: List[str]) -> List[str]:
    errors = []
    for field in fields:
        if field in section and not isinstance(section.get(field), str):
            errors.append("config {0}.{1} must be a string".format(section_name, field))
    return errors


def config_contract_errors(config: Dict) -> List[str]:
    errors = []
    if not isinstance(config, dict):
        return ["config must be an object"]

    run = config.get("run", {})
    if not isinstance(run, dict):
        errors.append("config run must be a mapping")
    else:
        if "parallelism" in run and not _is_positive_int(run.get("parallelism")):
            errors.append("config run.parallelism must be a positive integer")
        if "timeout_sec" in run and not _is_positive_int(run.get("timeout_sec")):
            errors.append("config run.timeout_sec must be a positive integer")
        if "output_dir" in run:
            errors.extend(output_dir_errors(run.get("output_dir")))
        if "task_instances" in run:
            task_instances = run.get("task_instances")
            if not isinstance(task_instances, list):
                errors.append("config run.task_instances must be a list of task instance labels")
            elif any(not isinstance(task_instance, str) for task_instance in task_instances):
                errors.append("config run.task_instances must be a list of task instance labels")

    for section in ("agent", "judge", "env", "docker", "runtime_inputs"):
        if section in config and not isinstance(config.get(section), dict):
            errors.append("config {0} must be a mapping".format(section))

    agent = config.get("agent", {})
    if isinstance(agent, dict):
        errors.extend(
            _string_field_errors(
                "agent",
                agent,
                ["type", "provider", "mode", "model", "base_url", "api_key_env"],
            )
        )

    judge = config.get("judge", {})
    if isinstance(judge, dict):
        errors.extend(_string_field_errors("judge", judge, ["base_url", "api_key_env", "model"]))

    docker = config.get("docker", {})
    if isinstance(docker, dict):
        if "enabled" in docker and not _is_bool(docker.get("enabled")):
            errors.append("config docker.enabled must be a boolean")
        if "build" in docker and not _is_bool(docker.get("build")):
            errors.append("config docker.build must be a boolean")
        if "image" in docker and not isinstance(docker.get("image"), str):
            errors.append("config docker.image must be a string")
        if "network" in docker and not isinstance(docker.get("network"), str):
            errors.append("config docker.network must be a string")

    runtime_inputs = config.get("runtime_inputs", {})
    if isinstance(runtime_inputs, dict):
        for input_id, definition in runtime_inputs.items():
            if not isinstance(definition, dict):
                errors.append("config runtime_inputs.{0} must be a mapping".format(input_id))
                continue
            errors.extend(
                _string_field_errors(
                    "runtime_inputs.{0}".format(input_id),
                    definition,
                    [
                        "schema",
                        "source",
                        "path",
                        "json",
                        "app_id_env",
                        "seller_id_env",
                        "gateway_env",
                        "sign_type_env",
                        "merchant_private_key_pkcs8_env",
                        "merchant_private_key_pkcs1_env",
                        "alipay_public_key_env",
                        "sandbox_buyer_account_env",
                        "sandbox_buyer_login_password_env",
                        "sandbox_buyer_pay_password_env",
                        "miniapp_app_id_env",
                        "op_app_id_env",
                    ],
                )
            )

    return errors
