import unittest
from pathlib import Path


class SaaSStartupContractTests(unittest.TestCase):
    REPO_ROOT = Path(__file__).resolve().parents[1]
    TASK_ROOT = REPO_ROOT / "benchmark_suite" / "task_instances"
    TASKS = {
        "SaaSStarter-MerchantInitiatedTransaction-basic": {
            "allow_unsigned": "true",
            "sync_postgres_url": False,
        },
        "SaaSStarter-MerchantInitiatedTransaction-advanced": {
            "allow_unsigned": "false",
            "sync_postgres_url": True,
        },
    }

    def _evaluation_script(self, task_instance: str) -> str:
        return (
            self.TASK_ROOT / task_instance / "evaluation" / "evaluate.sh"
        ).read_text(encoding="utf-8")

    def test_saas_evaluation_starts_fixture_before_integration(self):
        for task_instance in self.TASKS:
            with self.subTest(task_instance=task_instance):
                script = self._evaluation_script(task_instance)
                required = [
                    "pick_free_port()",
                    'MOCK_PORT="${ALIPAY_MOCK_PORT:-$(pick_free_port)}"',
                    'APP_PORT="${APP_PORT:-$(pick_free_port)}"',
                    'python3 "$support_dir/tests/mock_alipay_server.py"',
                    "export PAYSKILLS_TOP_LEVEL_START=1",
                    '(cd "$workspace" && bash start.sh)',
                ]
                for fragment in required:
                    self.assertIn(fragment, script)

                self.assertLess(
                    script.index('(cd "$workspace" && bash start.sh)'),
                    script.index('python3 "$deterministic_dir/integration.py"'),
                )

    def test_saas_evaluation_preserves_v3_runtime_variants(self):
        for task_instance, expected in self.TASKS.items():
            with self.subTest(task_instance=task_instance):
                script = self._evaluation_script(task_instance)
                self.assertIn(
                    "export ALIPAY_ALLOW_UNSIGNED_NOTIFY=\"${ALIPAY_ALLOW_UNSIGNED_NOTIFY:-"
                    + expected["allow_unsigned"]
                    + '}"',
                    script,
                )
                self.assertEqual(
                    "synced POSTGRES_URL from project .env" in script,
                    expected["sync_postgres_url"],
                )

    def test_saas_evaluation_cleans_up_mock_and_project_processes(self):
        for task_instance in self.TASKS:
            with self.subTest(task_instance=task_instance):
                script = self._evaluation_script(task_instance)
                self.assertIn('kill "$MOCK_PID"', script)
                self.assertIn('$workspace/.case-runtime/app.pid', script)


if __name__ == "__main__":
    unittest.main()
