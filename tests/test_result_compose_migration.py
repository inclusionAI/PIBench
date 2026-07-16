import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from payskills_runtime.result import main as result_main
from payskills_runtime.result.scoring import compose_result


class ComposeCompatibilityTests(unittest.TestCase):
    def test_invalid_rubric_fails_closed(self):
        definitions = {
            "rubrics": [
                {"id": "integration.invalid", "type": "deterministic", "weight": 1}
            ]
        }
        source = {
            "rubrics": [
                {
                    "id": "integration.invalid",
                    "passed": True,
                    "score": 1,
                    "max_score": 1,
                    "invalid": True,
                    "message": "test did not produce a valid verdict",
                }
            ]
        }

        result = compose_result(definitions, [source])

        self.assertEqual(result["score"], 0.0)
        self.assertFalse(result["rubrics"][0]["passed"])
        self.assertEqual(result["rubrics"][0]["score"], 0.0)
        self.assertTrue(result["rubrics"][0]["invalid"])
        self.assertIn(
            {"rubric_id": "integration.invalid", "error": "invalid_rubric_result"},
            result["metadata"]["compose_errors"],
        )

    def test_compose_preserves_source_rubric_diagnostics(self):
        definitions = {
            "rubrics": [
                {"id": "static.one", "type": "deterministic", "weight": 1},
                {"id": "integration.one", "type": "deterministic", "weight": 3},
            ]
        }
        source = {
            "score": 1.0,
            "rubrics": [
                {
                    "id": "static.one",
                    "passed": True,
                    "score": 1,
                    "max_score": 1,
                    "message": "kept",
                    "evidence": ["checks/static.json"],
                    "phase": "static",
                },
                {
                    "id": "integration.one",
                    "passed": False,
                    "score": 0,
                    "max_score": 1,
                    "message": "failed as before",
                    "test_infra_failure": True,
                },
            ],
        }

        result = compose_result(definitions, [source])

        self.assertEqual(result["score"], 0.25)
        self.assertEqual([item["passed"] for item in result["rubrics"]], [True, False])
        self.assertEqual(result["rubrics"][0]["evidence"], ["checks/static.json"])
        self.assertEqual(result["rubrics"][0]["phase"], "static")
        self.assertTrue(result["rubrics"][1]["test_infra_failure"])

    def test_compose_cli_inherits_compatibility_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rubric_file = root / "rubrics.json"
            source_file = root / "legacy-result.json"
            output_file = root / "result.json"
            rubric_file.write_text(
                json.dumps({"rubrics": [{"id": "r1", "weight": 2}]}),
                encoding="utf-8",
            )
            source_file.write_text(
                json.dumps(
                    {
                        "score": 0,
                        "rubrics": [
                            {"id": "r1", "passed": True, "score": 1, "max_score": 1}
                        ],
                        "metadata": {
                            "retryable_infra_failure": True,
                            "llm_judge_infra_failure": True,
                            "no_op_submission": False,
                        },
                    }
                ),
                encoding="utf-8",
            )

            exit_code = result_main(
                [
                    "compose",
                    "--rubric-file",
                    str(rubric_file),
                    "--input",
                    str(source_file),
                    "--metadata-file",
                    str(source_file),
                    "--output",
                    str(output_file),
                ]
            )

            self.assertEqual(exit_code, 0)
            result = json.loads(output_file.read_text(encoding="utf-8"))
            self.assertEqual(result["score"], 1.0)
            self.assertTrue(result["metadata"]["retryable_infra_failure"])
            self.assertTrue(result["metadata"]["llm_judge_infra_failure"])
            self.assertFalse(result["metadata"]["no_op_submission"])

    def test_compatibility_metadata_cannot_override_canonical_scoring(self):
        definitions = {"rubrics": [{"id": "r1", "weight": 2}]}
        source = {
            "rubrics": [{"id": "r1", "passed": True, "score": 1, "max_score": 1}],
            "metadata": {
                "scoring_policy": "legacy_unweighted",
                "raw_score": 999,
                "raw_max_score": 0,
                "weight_sum": 0,
                "missing_rubrics": ["fake"],
                "compose_errors": [{"error": "fake"}],
                "retryable_infra_failure": True,
            },
        }

        result = compose_result(definitions, [source], metadata=source["metadata"])

        self.assertEqual(result["metadata"]["scoring_policy"], "case_weighted_v1")
        self.assertEqual(result["metadata"]["raw_score"], 1.0)
        self.assertEqual(result["metadata"]["raw_max_score"], 1.0)
        self.assertEqual(result["metadata"]["weight_sum"], 2.0)
        self.assertEqual(result["metadata"]["missing_rubrics"], [])
        self.assertEqual(result["metadata"]["compose_errors"], [])
        self.assertTrue(result["metadata"]["retryable_infra_failure"])
        self.assertEqual(result["metadata"]["input_metadata"][0]["raw_score"], 999)


class EvaluationWiringTests(unittest.TestCase):
    REPO_ROOT = Path(__file__).resolve().parents[1]
    BASIC_TASK_INSTANCES = [
        "EZTickets-InAppPayment-basic",
        "LaravelGymie-JSAPIPayment-basic",
        "Litemall-PCWebPayment-basic",
        "SaaSStarter-MerchantInitiatedTransaction-basic",
    ]
    ADVANCED_TASK_INSTANCES = [
        "EZTickets-InAppPayment-advanced",
        "LaravelGymie-JSAPIPayment-advanced",
        "Litemall-PCWebPayment-advanced",
        "SaaSStarter-MerchantInitiatedTransaction-advanced",
    ]

    def assert_uses_canonical_compose(self, task_instance):
        script = (
            self.REPO_ROOT
            / "benchmark_suite"
            / "task_instances"
            / task_instance
            / "evaluation"
            / "evaluate.sh"
        ).read_text(encoding="utf-8")
        self.assertIn("payskills-result compose", script)
        self.assertIn("evaluation/rubrics.json", script)
        self.assertIn("--metadata-file", script)
        self.assertIn("--agent-file", script)

    def assert_fallback_cannot_leave_legacy_result(self, task_instance):
        script = (
            self.REPO_ROOT
            / "benchmark_suite"
            / "task_instances"
            / task_instance
            / "evaluation"
            / "evaluate.sh"
        ).read_text(encoding="utf-8")
        self.assertIn("if ! payskills-result compose", script)
        self.assertRegex(script, r'rm -f "\$(?:output_dir|OUTPUT_DIR)/result\.json"')
        self.assertIn("if ! payskills-result fallback", script)
        self.assertIn("exit 1", script)

    def test_basic_scenarios_use_canonical_compose(self):
        for task_instance in self.BASIC_TASK_INSTANCES:
            with self.subTest(task_instance=task_instance):
                self.assert_uses_canonical_compose(task_instance)

    def test_advanced_scenarios_use_canonical_compose(self):
        for task_instance in self.ADVANCED_TASK_INSTANCES:
            with self.subTest(task_instance=task_instance):
                self.assert_uses_canonical_compose(task_instance)

    def test_every_task_instance_uses_canonical_compose_without_legacy_normalizer(self):
        task_roots = sorted(
            path
            for path in (self.REPO_ROOT / "benchmark_suite/task_instances").iterdir()
            if path.is_dir()
        )
        self.assertEqual(len(task_roots), 18)
        for task_root in task_roots:
            with self.subTest(task_instance=task_root.name):
                script = (task_root / "evaluation/evaluate.sh").read_text(encoding="utf-8")
                self.assertIn("payskills-result compose", script)
                self.assertNotIn("normalize_result.py", script)

    def test_migrated_scripts_fail_closed_when_composition_cannot_finish(self):
        for task_instance in self.BASIC_TASK_INSTANCES + self.ADVANCED_TASK_INSTANCES:
            with self.subTest(task_instance=task_instance):
                self.assert_fallback_cannot_leave_legacy_result(task_instance)

    def test_evaluation_exits_nonzero_without_stale_result_when_compose_and_fallback_fail(self):
        task_root = self.REPO_ROOT / "benchmark_suite/task_instances/EZTickets-InAppPayment-basic"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output_dir = root / "output"
            workspace = root / "workspace"
            bin_dir = root / "bin"
            output_dir.mkdir()
            workspace.mkdir()
            bin_dir.mkdir()

            fake_python = bin_dir / "python3"
            fake_python.write_text(
                """#!/usr/bin/env bash
if [[ "$1" == *build_result.py ]]; then
  output_dir="$2"
  printf '{"version":"1.0","score":1,"max_score":1,"summary":"legacy","rubrics":[],"metadata":{}}\n' > "$output_dir/result.json"
fi
exit 0
""",
                encoding="utf-8",
            )
            fake_python.chmod(0o755)
            fake_result = bin_dir / "payskills-result"
            fake_result.write_text("#!/usr/bin/env bash\nexit 1\n", encoding="utf-8")
            fake_result.chmod(0o755)
            fake_pkill = bin_dir / "pkill"
            fake_pkill.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
            fake_pkill.chmod(0o755)

            env = dict(os.environ)
            env.update(
                {
                    "PATH": f"{bin_dir}:/usr/bin:/bin",
                    "TASK_INSTANCE_DIR": str(task_root),
                    "OUTPUT_DIR": str(output_dir),
                    "WORKSPACE": str(workspace),
                }
            )
            completed = subprocess.run(
                ["bash", str(task_root / "evaluation/evaluate.sh")],
                env=env,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(completed.returncode, 0)
            self.assertFalse((output_dir / "result.json").exists())

    def test_laravel_advanced_invalid_result_cannot_regain_credit(self):
        task_root = (
            self.REPO_ROOT
            / "benchmark_suite/task_instances/LaravelGymie-JSAPIPayment-advanced"
        )
        definitions = json.loads(
            (task_root / "evaluation/rubrics.json").read_text(encoding="utf-8")
        )
        rubric_id = definitions["rubrics"][0]["id"]

        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            (output_dir / "static_checks.json").write_text(
                json.dumps(
                    [
                        {
                            "id": rubric_id,
                            "passed": True,
                            "score": 1,
                            "max_score": 1,
                            "invalid": True,
                        }
                    ]
                ),
                encoding="utf-8",
            )
            (output_dir / "integration_results.json").write_text("[]", encoding="utf-8")
            (output_dir / "patch.diff").write_text("diff --git a/a b/a\n", encoding="utf-8")
            (output_dir / "changed_files.txt").write_text("a\n", encoding="utf-8")
            builder = task_root / "evaluation/deterministic/support/build_result.py"
            subprocess.run(
                ["python3", str(builder), str(output_dir)],
                check=True,
                capture_output=True,
                text=True,
            )
            result_path = output_dir / "result.json"
            before = json.loads(result_path.read_text(encoding="utf-8"))
            self.assertEqual(before["score"], 0.0)

            result_main(
                [
                    "compose",
                    "--rubric-file",
                    str(task_root / "evaluation/rubrics.json"),
                    "--input",
                    str(result_path),
                    "--metadata-file",
                    str(result_path),
                    "--output",
                    str(result_path),
                ]
            )
            after = json.loads(result_path.read_text(encoding="utf-8"))
            rubric = next(item for item in after["rubrics"] if item["id"] == rubric_id)
            self.assertEqual(after["score"], 0.0)
            self.assertFalse(rubric["passed"])
            self.assertEqual(rubric["score"], 0.0)

    def test_legacy_preparation_semantics_survive_weighted_compose(self):
        scenarios = [
            ("EZTickets-InAppPayment-basic", []),
            ("EZTickets-InAppPayment-advanced", []),
            ("LaravelGymie-JSAPIPayment-basic", []),
            ("LaravelGymie-JSAPIPayment-advanced", []),
            ("Litemall-PCWebPayment-basic", []),
            ("Litemall-PCWebPayment-advanced", []),
            (
                "SaaSStarter-MerchantInitiatedTransaction-basic",
                ["--mode", "basic", "--output-dir", "{output_dir}"],
            ),
            (
                "SaaSStarter-MerchantInitiatedTransaction-advanced",
                ["--mode", "safety", "--output-dir", "{output_dir}"],
            ),
        ]

        for task_instance, builder_args in scenarios:
            with self.subTest(task_instance=task_instance), tempfile.TemporaryDirectory() as tmp:
                output_dir = Path(tmp)
                task_root = (
                    self.REPO_ROOT
                    / "benchmark_suite"
                    / "task_instances"
                    / task_instance
                )
                builder = task_root / "evaluation/deterministic/support/build_result.py"
                command = ["python3", str(builder)]
                if builder_args:
                    command.extend(
                        value.format(output_dir=output_dir) for value in builder_args
                    )
                else:
                    command.append(str(output_dir))
                subprocess.run(command, check=True, capture_output=True, text=True)

                result_path = output_dir / "result.json"
                before = json.loads(result_path.read_text(encoding="utf-8"))
                before_by_id = {item["id"]: item for item in before["rubrics"]}
                result_main(
                    [
                        "compose",
                        "--rubric-file",
                        str(task_root / "evaluation/rubrics.json"),
                        "--input",
                        str(result_path),
                        "--metadata-file",
                        str(result_path),
                        "--agent-file",
                        str(output_dir / "agent_usage.json"),
                        "--output",
                        str(result_path),
                    ]
                )
                after = json.loads(result_path.read_text(encoding="utf-8"))
                after_by_id = {item["id"]: item for item in after["rubrics"]}

                self.assertTrue(set(before_by_id).issubset(after_by_id))
                for rubric_id, old in before_by_id.items():
                    new = after_by_id[rubric_id]
                    self.assertEqual(new["passed"], old["passed"])
                    self.assertEqual(new["score"], old["score"])
                    self.assertEqual(new["message"], old.get("message", "passed" if old["passed"] else "failed"))
                    if "evidence" in old:
                        self.assertEqual(new["evidence"], old["evidence"])
                    self.assertIn("weight", new)
                    self.assertIn("weighted_score", new)

                for rubric_id in set(after_by_id) - set(before_by_id):
                    self.assertFalse(after_by_id[rubric_id]["passed"])
                    self.assertTrue(after_by_id[rubric_id]["missing"])

                canonical_metadata = {
                    "scoring_policy",
                    "raw_score",
                    "raw_max_score",
                    "weighted_raw_score",
                    "weight_sum",
                    "missing_rubrics",
                    "extra_rubrics",
                    "compose_errors",
                    "input_metadata",
                    "input_summaries",
                }
                for key, value in before.get("metadata", {}).items():
                    if key not in canonical_metadata:
                        self.assertEqual(after["metadata"][key], value)
                self.assertEqual(after["metadata"]["scoring_policy"], "case_weighted_v1")
                expected = sum(item["weighted_score"] for item in after["rubrics"])
                expected /= sum(item["weight"] for item in after["rubrics"])
                self.assertAlmostEqual(after["score"], expected, places=9)


if __name__ == "__main__":
    unittest.main()
