import json
import os
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional


@dataclass(frozen=True)
class RuntimeInputRequirement:
    id: str
    schema: str = ""
    required: bool = False
    deliver_as: str = "file"
    env: str = ""
    workspace_path: str = ""


@dataclass(frozen=True)
class PreparedRuntimeInputs:
    env: Dict[str, str] = field(default_factory=dict)
    mounts: List[Dict[str, str]] = field(default_factory=list)
    workspace_files: List[Dict[str, str]] = field(default_factory=list)
    cleanup_paths: List[Path] = field(default_factory=list)


ALIPAY_SANDBOX_ENV_FIELDS = {
    "app_id": "app_id_env",
    "seller_id": "seller_id_env",
    "gateway": "gateway_env",
    "sign_type": "sign_type_env",
    "merchant_private_key_pkcs8": "merchant_private_key_pkcs8_env",
    "merchant_private_key_pkcs1": "merchant_private_key_pkcs1_env",
    "alipay_public_key": "alipay_public_key_env",
    "miniapp_app_id": "miniapp_app_id_env",
    "op_app_id": "op_app_id_env",
}
ALIPAY_SANDBOX_BUYER_ENV_FIELDS = {
    "account": "sandbox_buyer_account_env",
    "login_password": "sandbox_buyer_login_password_env",
    "pay_password": "sandbox_buyer_pay_password_env",
}
CONTAINER_RUNTIME_INPUT_DIR = "/run/payskills/inputs"


def _safe_id(value: str) -> str:
    return "".join(char if char.isalnum() else "_" for char in value.strip()).upper()


def _default_env_name(input_id: str) -> str:
    return "PAYSKILLS_RUNTIME_INPUT_{0}_FILE".format(_safe_id(input_id))


def _container_path(input_id: str) -> str:
    return "{0}/{1}.json".format(CONTAINER_RUNTIME_INPUT_DIR, _safe_id(input_id).lower())


def _safe_workspace_path(value: str) -> str:
    path = Path(str(value or "").strip())
    if not path:
        return ""
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("workspace_path must be a safe relative path")
    return path.as_posix()


def _parse_toml_scalar(value: str):
    value = value.strip()
    if value.lower() in {"true", "false"}:
        return value.lower() == "true"
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    return value


def task_runtime_input_requirements(task_instance_dir: Path) -> List[RuntimeInputRequirement]:
    path = Path(task_instance_dir) / "task_instance.toml"
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []

    requirements: List[RuntimeInputRequirement] = []
    current: Optional[Dict[str, object]] = None
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped == "[[runtime_inputs]]":
            if current:
                requirements.append(_requirement_from_mapping(current))
            current = {}
            continue
        if stripped.startswith("[") and stripped.endswith("]"):
            if current:
                requirements.append(_requirement_from_mapping(current))
                current = None
            continue
        if current is not None and "=" in stripped:
            key, value = stripped.split("=", 1)
            current[key.strip()] = _parse_toml_scalar(value)
    if current:
        requirements.append(_requirement_from_mapping(current))
    return requirements


def _requirement_from_mapping(payload: Mapping[str, object]) -> RuntimeInputRequirement:
    input_id = str(payload.get("id") or "").strip()
    return RuntimeInputRequirement(
        id=input_id,
        schema=str(payload.get("schema") or "").strip(),
        required=bool(payload.get("required", False)),
        deliver_as=str(payload.get("deliver_as") or "file").strip(),
        env=str(payload.get("env") or _default_env_name(input_id)).strip(),
        workspace_path=_safe_workspace_path(str(payload.get("workspace_path") or "").strip()),
    )


def _definition_for_requirement(
    requirement: RuntimeInputRequirement,
    config: Mapping[str, object],
    env: Mapping[str, str],
) -> Dict[str, object]:
    configured = config.get("runtime_inputs") if isinstance(config, Mapping) else {}
    if isinstance(configured, Mapping) and isinstance(configured.get(requirement.id), Mapping):
        return dict(configured.get(requirement.id) or {})

    env_prefix = "PAYSKILLS_RUNTIME_INPUT_{0}_".format(_safe_id(requirement.id))
    file_value = str(env.get(env_prefix + "FILE") or "").strip()
    if file_value:
        return {"schema": requirement.schema, "source": "file", "path": file_value}
    json_value = str(env.get(env_prefix + "JSON") or "").strip()
    if json_value:
        return {"schema": requirement.schema, "source": "json", "json": json_value}
    return {}


def _config_base_dir(config: Mapping[str, object]) -> Path:
    configured = str(config.get("__config_dir") or "").strip() if isinstance(config, Mapping) else ""
    return Path(configured).resolve() if configured else Path.cwd()


def _resolve_source_file(path_text: str, config: Mapping[str, object]) -> Path:
    path = Path(path_text).expanduser()
    if not path.is_absolute():
        path = _config_base_dir(config) / path
    return path.resolve()


def _write_materialized_json(input_id: str, payload: Mapping[str, object]) -> Path:
    directory = Path(tempfile.mkdtemp(prefix="payskills_runtime_input_"))
    path = directory / "{0}.json".format(_safe_id(input_id).lower())
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    try:
        path.chmod(0o444)
    except OSError:
        pass
    return path


def _write_mountable_file(input_id: str, source: Path) -> Path:
    directory = Path(tempfile.mkdtemp(prefix="payskills_runtime_input_"))
    path = directory / "{0}.json".format(_safe_id(input_id).lower())
    shutil.copyfile(source, path)
    try:
        path.chmod(0o444)
    except OSError:
        pass
    return path


def _alipay_sandbox_payload_from_env(definition: Mapping[str, object], env: Mapping[str, str]) -> Dict[str, object]:
    payload: Dict[str, object] = {}
    for output_field, env_field in ALIPAY_SANDBOX_ENV_FIELDS.items():
        env_name = str(definition.get(env_field) or "").strip()
        if env_name and env.get(env_name):
            payload[output_field] = env[env_name]
    buyer = {}
    for output_field, env_field in ALIPAY_SANDBOX_BUYER_ENV_FIELDS.items():
        env_name = str(definition.get(env_field) or "").strip()
        if env_name and env.get(env_name):
            buyer[output_field] = env[env_name]
    if buyer:
        payload["sandbox_buyer"] = buyer
    if "gateway" not in payload:
        payload["gateway"] = "https://openapi-sandbox.dl.alipaydev.com/gateway.do"
    if "sign_type" not in payload:
        payload["sign_type"] = "RSA2"
    return payload


def _host_file_for_definition(
    requirement: RuntimeInputRequirement,
    definition: Mapping[str, object],
    config: Mapping[str, object],
    env: Mapping[str, str],
) -> Path:
    source = str(definition.get("source") or "file").strip()
    if source == "file":
        path_text = str(definition.get("path") or "").strip()
        if not path_text:
            raise ValueError("runtime input {0} source=file requires path".format(requirement.id))
        path = _resolve_source_file(path_text, config)
        if not path.exists():
            raise ValueError("runtime input {0} file is missing".format(requirement.id))
        return path
    if source == "json":
        json_text = str(definition.get("json") or "").strip()
        if not json_text:
            raise ValueError("runtime input {0} source=json requires json".format(requirement.id))
        return _write_materialized_json(requirement.id, json.loads(json_text))
    if source == "env":
        if requirement.schema != "alipay.sandbox.v1":
            raise ValueError("runtime input {0} source=env is unsupported for schema {1}".format(requirement.id, requirement.schema))
        payload = _alipay_sandbox_payload_from_env(definition, env)
        if not payload.get("app_id"):
            raise ValueError("runtime input {0} source=env requires app_id_env".format(requirement.id))
        if not (payload.get("merchant_private_key_pkcs8") or payload.get("merchant_private_key_pkcs1")):
            raise ValueError("runtime input {0} source=env requires a merchant private key env".format(requirement.id))
        if not payload.get("alipay_public_key"):
            raise ValueError("runtime input {0} source=env requires alipay_public_key_env".format(requirement.id))
        return _write_materialized_json(requirement.id, payload)
    raise ValueError("runtime input {0} uses unsupported source {1}".format(requirement.id, source))


def _definition_error(
    requirement: RuntimeInputRequirement,
    definition: Mapping[str, object],
    config: Mapping[str, object],
    env: Mapping[str, str],
) -> str:
    source = str(definition.get("source") or "file").strip()
    if requirement.schema and str(definition.get("schema") or requirement.schema) != requirement.schema:
        return "runtime input {0} schema mismatch".format(requirement.id)
    if source == "file":
        path_text = str(definition.get("path") or "").strip()
        if not path_text:
            return "runtime input {0} source=file requires path".format(requirement.id)
        if not _resolve_source_file(path_text, config).exists():
            return "runtime input {0} file is missing".format(requirement.id)
        return ""
    if source == "json":
        json_text = str(definition.get("json") or "").strip()
        if not json_text:
            return "runtime input {0} source=json requires json".format(requirement.id)
        try:
            json.loads(json_text)
        except Exception:
            return "runtime input {0} source=json is invalid json".format(requirement.id)
        return ""
    if source == "env":
        if requirement.schema != "alipay.sandbox.v1":
            return "runtime input {0} source=env is unsupported for schema {1}".format(requirement.id, requirement.schema)
        payload = _alipay_sandbox_payload_from_env(definition, env)
        if not payload.get("app_id"):
            return "runtime input {0} source=env requires app_id_env".format(requirement.id)
        if not (payload.get("merchant_private_key_pkcs8") or payload.get("merchant_private_key_pkcs1")):
            return "runtime input {0} source=env requires a merchant private key env".format(requirement.id)
        if not payload.get("alipay_public_key"):
            return "runtime input {0} source=env requires alipay_public_key_env".format(requirement.id)
        return ""
    return "runtime input {0} uses unsupported source {1}".format(requirement.id, source)


def runtime_input_errors(
    task_instances: Iterable[Mapping[str, object]],
    config: Mapping[str, object],
    *,
    env: Optional[Mapping[str, str]] = None,
) -> List[str]:
    env_map = dict(os.environ if env is None else env)
    errors: List[str] = []
    for task_instance in task_instances:
        task_instance_dir = Path(task_instance["path"])
        label = str(task_instance.get("label") or task_instance.get("name") or task_instance_dir.name)
        for requirement in task_runtime_input_requirements(task_instance_dir):
            definition = _definition_for_requirement(requirement, config, env_map)
            if not definition:
                if requirement.required:
                    errors.append(
                        "task instance {0} requires runtime input {1} but it is not configured".format(
                            label,
                            requirement.id,
                        )
                    )
                continue
            error = _definition_error(requirement, definition, config, env_map)
            if error:
                errors.append("task instance {0}: {1}".format(label, error))
    return errors


def prepare_runtime_inputs(
    task_instance_dir: Path,
    config: Mapping[str, object],
    *,
    output_dir: Optional[Path] = None,
    env: Optional[Mapping[str, str]] = None,
) -> PreparedRuntimeInputs:
    del output_dir
    env_map = dict(os.environ if env is None else env)
    prepared_env: Dict[str, str] = {}
    mounts: List[Dict[str, str]] = []
    workspace_files: List[Dict[str, str]] = []
    cleanup_paths: List[Path] = []

    for requirement in task_runtime_input_requirements(task_instance_dir):
        if requirement.deliver_as and requirement.deliver_as != "file":
            raise ValueError("runtime input {0} deliver_as={1} is unsupported".format(requirement.id, requirement.deliver_as))
        definition = _definition_for_requirement(requirement, config, env_map)
        if not definition:
            if requirement.required:
                raise ValueError("runtime input {0} is required but not configured".format(requirement.id))
            continue
        if requirement.schema and str(definition.get("schema") or requirement.schema) != requirement.schema:
            raise ValueError("runtime input {0} schema mismatch".format(requirement.id))
        source_file = _host_file_for_definition(requirement, definition, config, env_map)
        host_file = _write_mountable_file(requirement.id, source_file)
        cleanup_paths.append(host_file.parent)
        container_path = _container_path(requirement.id)
        prepared_env[requirement.env] = str(host_file)
        mount = {
            "host_path": str(host_file),
            "container_path": container_path,
            "env": requirement.env,
        }
        if requirement.workspace_path:
            mount["workspace_path"] = requirement.workspace_path
            workspace_files.append(
                {
                    "host_path": str(host_file),
                    "workspace_path": requirement.workspace_path,
                }
            )
        mounts.append(mount)
    return PreparedRuntimeInputs(
        env=prepared_env,
        mounts=mounts,
        workspace_files=workspace_files,
        cleanup_paths=cleanup_paths,
    )


def container_runtime_input_env(prepared: PreparedRuntimeInputs) -> Dict[str, str]:
    env = dict(prepared.env)
    for mount in prepared.mounts:
        env[mount["env"]] = mount["container_path"]
    return env


def copy_runtime_inputs_to_workspace(prepared: PreparedRuntimeInputs, workspace_dir: Path) -> None:
    workspace = Path(workspace_dir)
    for item in prepared.workspace_files:
        destination = workspace / item["workspace_path"]
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item["host_path"], destination)
