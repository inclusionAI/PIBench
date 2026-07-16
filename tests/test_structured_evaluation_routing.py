import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import payskills_runtime.task_instance as task_instance_runtime
from payskills_runtime.task_instance import discover_task_instances
from payskills_runtime.task_instance.execution import (
    TaskInstanceExecutionSpec,
    execute_task_instance,
)


class StructuredTaskMetadataTests(unittest.TestCase):
    REPO_ROOT = Path(__file__).resolve().parents[1]

    def test_runtime_exports_canonical_task_metadata(self):
        self.assertTrue(
            hasattr(task_instance_runtime, "task_instance_runtime_env"),
            "runtime must expose structured task metadata to task scripts",
        )
        task = next(
            item
            for item in discover_task_instances(self.REPO_ROOT / "benchmark_suite")
            if item["name"] == "BillExpress-OrderQRCodePayment-advanced"
        )

        runtime_env = task_instance_runtime.task_instance_runtime_env(task["path"], task)

        self.assertEqual(runtime_env["PAYSKILLS_TASK_INSTANCE_ID"], task["name"])
        self.assertEqual(runtime_env["PAYSKILLS_PROJECT"], "BillExpress")
        self.assertEqual(runtime_env["PAYSKILLS_PRODUCT"], "OrderQRCodePayment")
        self.assertEqual(runtime_env["PAYSKILLS_SCENARIO"], "advanced")
        self.assertEqual(runtime_env["CASE_NAME"], task["name"])
        self.assertEqual(runtime_env["PAYSKILLS_CASE_NAME"], task["name"])

    def test_toml_routing_metadata_overrides_stale_caller_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            task_root = Path(tmp)
            (task_root / "task_instance.toml").write_text(
                """[task_instance]
name = "CanonicalTask-basic"
project = "CanonicalProject"
product = "CanonicalProduct"
scenario = "basic"
""",
                encoding="utf-8",
            )

            runtime_env = task_instance_runtime.task_instance_runtime_env(
                task_root,
                {
                    "name": "CanonicalTask-basic",
                    "project": "StaleProject",
                    "product": "StaleProduct",
                    "scenario": "advanced",
                },
            )

            self.assertEqual(runtime_env["PAYSKILLS_PROJECT"], "CanonicalProject")
            self.assertEqual(runtime_env["PAYSKILLS_PRODUCT"], "CanonicalProduct")
            self.assertEqual(runtime_env["PAYSKILLS_SCENARIO"], "basic")

    def test_task_and_evaluation_processes_receive_canonical_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            task_root = root / "task-instance"
            workspace = root / "workspace"
            output = root / "output"
            (task_root / "task").mkdir(parents=True)
            (task_root / "evaluation").mkdir()
            (task_root / "task_instance.toml").write_text(
                """[task_instance]
name = "RenamedTask-basic"
project = "ProjectName"
product = "ProductName"
scenario = "basic"
""",
                encoding="utf-8",
            )
            (task_root / "task/run.sh").write_text(
                'env | sort > "$OUTPUT_DIR/run.env"\n', encoding="utf-8"
            )
            (task_root / "evaluation/evaluate.sh").write_text(
                """env | sort > "$OUTPUT_DIR/evaluation.env"
printf '%s\n' '{"version":"1.0","score":1,"max_score":1,"summary":"ok","rubrics":[],"metadata":{}}' > "$OUTPUT_DIR/result.json"
""",
                encoding="utf-8",
            )

            executed = execute_task_instance(
                TaskInstanceExecutionSpec(
                    task_instance_dir=task_root,
                    workspace_dir=workspace,
                    output_dir=output,
                    kit_dir=self.REPO_ROOT / "src",
                    run_script=Path("task/run.sh"),
                    evaluation_script=Path("evaluation/evaluate.sh"),
                    timeout_sec=30,
                    task_instance={
                        "name": "RenamedTask-basic",
                        "version": "v0",
                        "label": "RenamedTask-basic",
                    },
                )
            )

            self.assertEqual(executed.run_exit, 0)
            self.assertEqual(executed.evaluation_exit, 0)
            for filename in ("run.env", "evaluation.env"):
                values = dict(
                    line.split("=", 1)
                    for line in (output / filename).read_text(encoding="utf-8").splitlines()
                    if "=" in line
                )
                self.assertEqual(values["PAYSKILLS_TASK_INSTANCE_ID"], "RenamedTask-basic")
                self.assertEqual(values["PAYSKILLS_PROJECT"], "ProjectName")
                self.assertEqual(values["PAYSKILLS_PRODUCT"], "ProductName")
                self.assertEqual(values["PAYSKILLS_SCENARIO"], "basic")
                self.assertEqual(values["CASE_NAME"], "RenamedTask-basic")


class EvaluationRoutingTests(unittest.TestCase):
    REPO_ROOT = Path(__file__).resolve().parents[1]
    TASK_ROOT = REPO_ROOT / "benchmark_suite" / "task_instances"
    BILL_VARIANTS = {
        "BillExpress-OrderQRCodePayment-basic": "qrcode_basic",
        "BillExpress-OrderQRCodePayment-advanced": "qrcode_safety",
        "BillExpress-QRCodePayment-basic": "barcode_basic",
        "BillExpress-QRCodePayment-advanced": "barcode_safety",
    }

    @staticmethod
    def _load_common(task_root):
        path = task_root / "evaluation" / "deterministic" / "support" / "common.py"
        module_name = "routing_" + task_root.name.replace("-", "_")
        spec = importlib.util.spec_from_file_location(module_name, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_bill_express_routes_from_structured_product_and_scenario(self):
        tasks = {
            item["name"]: item
            for item in discover_task_instances(self.REPO_ROOT / "benchmark_suite")
        }
        for task_name, expected in self.BILL_VARIANTS.items():
            with self.subTest(task_instance=task_name):
                task = tasks[task_name]
                common = self._load_common(Path(task["path"]))
                env = {
                    "PAYSKILLS_PRODUCT": str(task["product"]),
                    "PAYSKILLS_SCENARIO": str(task["scenario"]),
                }
                with mock.patch.dict(os.environ, env, clear=False):
                    try:
                        actual = common.case_kind()
                    except TypeError:
                        # The legacy implementation requires the renamed task ID
                        # and demonstrates the name-coupling regression.
                        actual = common.case_kind(task_name)
                self.assertEqual(actual, expected)

    def test_bill_express_variant_rubrics_exactly_match_definitions(self):
        for task_name, variant in self.BILL_VARIANTS.items():
            with self.subTest(task_instance=task_name):
                task_root = self.TASK_ROOT / task_name
                common = self._load_common(task_root)
                definitions = json.loads(
                    (task_root / "evaluation/rubrics.json").read_text(encoding="utf-8")
                )
                definition_ids = {item["id"] for item in definitions["rubrics"]}
                self.assertEqual(set(common.EXPECTED[variant]), definition_ids)

    def test_bill_express_root_key_materialization_matches_v3_contract(self):
        root_key_writer = (
            'Path(os.environ["WORKSPACE"], "alipay-sandbox-keys.json")'
            ".write_text(config_text)"
        )
        tasks_with_root_key_writer = {
            task_name
            for task_name in self.BILL_VARIANTS
            if root_key_writer
            in (self.TASK_ROOT / task_name / "evaluation/evaluate.sh").read_text(
                encoding="utf-8"
            )
        }

        self.assertEqual(
            tasks_with_root_key_writer,
            {"BillExpress-OrderQRCodePayment-basic"},
        )

    def test_bill_express_advanced_mock_keys_are_separated_from_workspace(self):
        for task_name, product in (
            ("BillExpress-OrderQRCodePayment-advanced", "OrderQRCodePayment"),
            ("BillExpress-QRCodePayment-advanced", "QRCodePayment"),
        ):
            with self.subTest(task_instance=task_name), tempfile.TemporaryDirectory() as tmp:
                workspace = Path(tmp) / "workspace"
                output = Path(tmp) / "static.json"
                workspace.mkdir()
                for required in ("package.json", "start.sh", "server.ts"):
                    (workspace / required).write_text("", encoding="utf-8")
                env = dict(os.environ)
                env.update(
                    PAYSKILLS_PRODUCT=product,
                    PAYSKILLS_SCENARIO="advanced",
                )

                completed = subprocess.run(
                    [
                        sys.executable,
                        str(self.TASK_ROOT / task_name / "evaluation/deterministic/static.py"),
                        str(workspace),
                        str(output),
                        task_name,
                    ],
                    env=env,
                    capture_output=True,
                    text=True,
                )

                self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
                payload = json.loads(output.read_text(encoding="utf-8"))
                rubric = next(
                    item
                    for item in payload["rubrics"]
                    if item["id"] == "static.mock_key_separation"
                )
                self.assertTrue(rubric["passed"], rubric["evidence"])

    def test_bookcars_static_normalization_uses_structured_scenario(self):
        scenarios = [
            ("BookCars-AuthorizationHold-basic", "basic", "S1", 1.0),
            (
                "BookCars-AuthorizationHold-advanced",
                "advanced",
                "preauth_pay_auth_no",
                15.0,
            ),
        ]
        for task_name, scenario, rubric_id, expected_max in scenarios:
            with self.subTest(task_instance=task_name), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                workspace = root / "workspace"
                output = root / "static.json"
                workspace.mkdir()
                env = dict(os.environ)
                env["PAYSKILLS_SCENARIO"] = scenario
                completed = subprocess.run(
                    [
                        sys.executable,
                        str(self.TASK_ROOT / task_name / "evaluation/deterministic/static.py"),
                        str(workspace),
                        str(output),
                        "identifier-without-legacy-routing-tokens",
                    ],
                    env=env,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
                payload = json.loads(output.read_text(encoding="utf-8"))
                rubric = next(item for item in payload["rubrics"] if item["id"] == rubric_id)
                self.assertEqual(rubric["max_score"], expected_max)

    def test_bookcars_fallback_and_postprocess_use_structured_scenario(self):
        scenarios = [
            ("BookCars-AuthorizationHold-basic", "basic", 9, 2, 0.5),
            ("BookCars-AuthorizationHold-advanced", "advanced", 17, 1, 0.0),
        ]
        for task_name, scenario, integration_count, e2e_count, final_score in scenarios:
            with self.subTest(task_instance=task_name), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                support = self.TASK_ROOT / task_name / "evaluation/deterministic/support"
                env = dict(os.environ)
                env["PAYSKILLS_SCENARIO"] = scenario

                for phase, expected_count in (
                    ("integration", integration_count),
                    ("e2e", e2e_count),
                ):
                    output = root / (phase + ".json")
                    completed = subprocess.run(
                        [
                            sys.executable,
                            str(support / "write_fallback.py"),
                            phase,
                            "identifier-without-legacy-routing-tokens",
                            str(output),
                        ],
                        env=env,
                        capture_output=True,
                        text=True,
                    )
                    self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
                    payload = json.loads(output.read_text(encoding="utf-8"))
                    self.assertEqual(len(payload["rubrics"]), expected_count)

                result = {
                    "score": 0.5,
                    "summary": "probe",
                    "rubrics": [
                        {"id": "I1", "type": "deterministic", "test_infra_failure": True},
                        {"id": "E1", "type": "deterministic", "test_infra_failure": True},
                    ],
                    "metadata": {},
                }
                (root / "result.json").write_text(json.dumps(result), encoding="utf-8")
                completed = subprocess.run(
                    [
                        sys.executable,
                        str(support / "postprocess_result.py"),
                        str(root),
                        "identifier-without-legacy-routing-tokens",
                    ],
                    env=env,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
                payload = json.loads((root / "result.json").read_text(encoding="utf-8"))
                self.assertEqual(payload["score"], final_score)
                self.assertEqual(
                    bool(payload["metadata"].get("runtime_infra_failure")),
                    scenario == "advanced",
                )

    def test_evaluators_do_not_dispatch_on_task_name_substrings(self):
        forbidden = [
            re.compile(r'["\'](?:qrcode|barcode|safety)["\']\s+in\s+case_name'),
            re.compile(r'case_kind\(case_name\)'),
            re.compile(r'\$case_name["}]?\s*==\s*\*(?:qrcode|barcode|safety)\*'),
        ]
        findings = []
        task_roots = sorted(self.TASK_ROOT.glob("BillExpress-*"))
        task_roots += sorted(self.TASK_ROOT.glob("BookCars-*"))
        for task_root in task_roots:
            for path in sorted((task_root / "evaluation").rglob("*")):
                if not path.is_file() or path.suffix not in {".py", ".sh"}:
                    continue
                text = path.read_text(encoding="utf-8", errors="replace")
                for pattern in forbidden:
                    for match in pattern.finditer(text):
                        line = text.count("\n", 0, match.start()) + 1
                        findings.append(f"{path.relative_to(self.REPO_ROOT)}:{line}: {match.group(0)}")

        self.assertEqual(findings, [], "\n".join(findings))

    def test_legacy_case_metadata_labels_are_not_emitted(self):
        files = [
            self.TASK_ROOT
            / "EZTickets-InAppPayment-advanced"
            / "evaluation/deterministic/support/build_result.py",
            self.TASK_ROOT
            / "LaravelGymie-JSAPIPayment-advanced"
            / "evaluation/deterministic/support/build_result.py",
        ]
        combined = "\n".join(path.read_text(encoding="utf-8") for path in files)
        self.assertNotIn('"case": "ez_tickets-alipay-safety"', combined)
        self.assertNotIn("'case': 'jsapi-trade-security'", combined)


if __name__ == "__main__":
    unittest.main()
