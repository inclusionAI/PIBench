import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


class A2MWorkspaceSetupTests(unittest.TestCase):
    REPO_ROOT = Path(__file__).resolve().parents[1]
    TASK_ROOT = (
        REPO_ROOT
        / "benchmark_suite"
        / "task_instances"
        / "A2MRecipes-UsageBasedPayment-basic"
    )

    def test_run_script_seeds_preinstalled_dependencies_before_agent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "workspace"
            output = root / "output"
            template = root / "app-template"
            bin_dir = root / "bin"
            workspace.mkdir()
            output.mkdir()
            (template / "node_modules").mkdir(parents=True)
            bin_dir.mkdir()

            fixture = self.TASK_ROOT / "task" / "fixtures" / "project"
            shutil.copy2(fixture / "package.json", workspace / "package.json")
            shutil.copy2(fixture / "pnpm-lock.yaml", workspace / "pnpm-lock.yaml")
            shutil.copy2(fixture / "pnpm-lock.yaml", template / "pnpm-lock.yaml")
            (template / "node_modules" / ".seed-marker").write_text(
                "seeded\n", encoding="utf-8"
            )

            agent = bin_dir / "payskills-agent"
            agent.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
            agent.chmod(0o755)

            script = root / "run.sh"
            script.write_text(
                (self.TASK_ROOT / "task" / "run.sh")
                .read_text(encoding="utf-8")
                .replace("/opt/app-template", str(template)),
                encoding="utf-8",
            )
            script.chmod(0o755)

            env = dict(os.environ)
            env.update(
                TASK_INSTANCE_DIR=str(self.TASK_ROOT),
                WORKSPACE=str(workspace),
                OUTPUT_DIR=str(output),
                AGENT_MODE="no-skill",
                AGENT_MODEL="test-model",
                PATH=str(bin_dir) + os.pathsep + env.get("PATH", ""),
            )
            completed = subprocess.run(
                ["bash", str(script)],
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=30,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, completed.stdout)
            self.assertTrue(
                (workspace / "node_modules" / ".seed-marker").is_file(),
                completed.stdout,
            )
            self.assertIn("[setup] seeding node_modules from", completed.stdout)


if __name__ == "__main__":
    unittest.main()
