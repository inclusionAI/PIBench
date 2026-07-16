import json
import unittest
from pathlib import Path

from payskills_runtime.config.contract import config_contract_errors
from payskills_runtime.execution.runtime_inputs import _alipay_sandbox_payload_from_env


class SellerIdentityContractTests(unittest.TestCase):
    REPO_ROOT = Path(__file__).resolve().parents[1]
    TASK_ROOT = REPO_ROOT / "benchmark_suite" / "task_instances"

    def test_env_runtime_input_materializes_canonical_seller_id(self):
        payload = _alipay_sandbox_payload_from_env(
            {"seller_id_env": "TEST_ALIPAY_SELLER_ID"},
            {"TEST_ALIPAY_SELLER_ID": "2088000000000001"},
        )

        self.assertEqual(payload["seller_id"], "2088000000000001")

    def test_config_contract_validates_seller_id_env_as_a_string(self):
        config = {
            "runtime_inputs": {
                "alipay_sandbox": {
                    "schema": "alipay.sandbox.v1",
                    "source": "env",
                    "seller_id_env": 123,
                }
            }
        }

        self.assertIn(
            "config runtime_inputs.alipay_sandbox.seller_id_env must be a string",
            config_contract_errors(config),
        )

    def test_release_configuration_documents_canonical_seller_id(self):
        for relative_path in (
            "config/config.yaml",
            "config/config.example.yaml",
            "config/.env.example",
            "README.md",
            "README.zh-CN.md",
        ):
            with self.subTest(path=relative_path):
                text = (self.REPO_ROOT / relative_path).read_text(encoding="utf-8")
                self.assertIn("ALIPAY_SELLER_ID", text)

        for relative_path in ("README.md", "README.zh-CN.md"):
            with self.subTest(path=relative_path):
                text = (self.REPO_ROOT / relative_path).read_text(encoding="utf-8")
                self.assertIn('"seller_id": "<your-sandbox-merchant-pid>"', text)
                self.assertIn('"app_id": "<your-sandbox-app-id>"', text)

    def test_directly_affected_evaluations_use_runtime_seller_id(self):
        expected_markers = {
            "EZTickets-InAppPayment-advanced/evaluation/evaluate.sh": (
                'data.get("seller_id")'
            ),
            "EZTickets-InAppPayment-advanced/evaluation/deterministic/support/integration_test.sh": (
                'export ALIPAY_SELLER_ID="${ALIPAY_SELLER_ID:-2088SELLEREVAL}"'
            ),
            "EDoc-MobileWebPayment-basic/evaluation/evaluate.sh": "data.get(\"seller_id\")",
            "LaravelGymie-JSAPIPayment-basic/task/run.sh": "data.get(\"seller_id\")",
            "LaravelGymie-JSAPIPayment-basic/evaluation/deterministic/support/integration_tests.py": (
                'os.environ.get("ALIPAY_SELLER_ID")'
            ),
            "Litemall-PCWebPayment-advanced/evaluation/deterministic/support/sign_utils.py": (
                '"seller_id": fixture.get("seller_id", "")'
            ),
            "Litemall-PCWebPayment-advanced/evaluation/deterministic/integration.py": (
                'SELLER_ID = os.environ.get("ALIPAY_SELLER_ID")'
            ),
        }
        for relative_path, marker in expected_markers.items():
            with self.subTest(path=relative_path):
                text = (self.TASK_ROOT / relative_path).read_text(encoding="utf-8")
                self.assertIn(marker, text)

    def test_eztickets_identity_rubric_uses_two_probes_but_one_result(self):
        task = self.TASK_ROOT / "EZTickets-InAppPayment-advanced"
        rubrics = json.loads(
            (task / "evaluation/rubrics.json").read_text(encoding="utf-8")
        )["rubrics"]
        source = (
            task / "evaluation/deterministic/support/integration_tests.js"
        ).read_text(encoding="utf-8")

        self.assertEqual(len(rubrics), 41)
        self.assertEqual([item["id"] for item in rubrics].count("I17"), 1)
        self.assertIn("wrong-app-only", source)
        self.assertIn("wrong-seller-only", source)
        self.assertEqual(source.count("record('I17'"), 1)
        self.assertIn(
            "ALIPAY_SELLER_ID",
            (task / "task/instruction.md").read_text(encoding="utf-8"),
        )


if __name__ == "__main__":
    unittest.main()
