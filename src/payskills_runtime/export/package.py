from pathlib import Path
from typing import List

from payskills_runtime.export.layout import REQUIRED_PACKAGE_PATHS, REQUIRED_RUNTIME_SOURCE_PATHS
from payskills_runtime.common.manifest_contract import manifest_contract_errors


def export_package_errors(export_root: Path) -> List[str]:
    errors = []
    errors.extend(manifest_contract_errors(export_root))
    for rel_path in REQUIRED_PACKAGE_PATHS:
        if not (export_root / rel_path).exists():
            errors.append("package is incomplete: missing {0}".format(rel_path))
    for rel_path in REQUIRED_RUNTIME_SOURCE_PATHS:
        if not (export_root / rel_path).exists():
            errors.append("runtime source is incomplete: missing {0}".format(rel_path))
    return errors
