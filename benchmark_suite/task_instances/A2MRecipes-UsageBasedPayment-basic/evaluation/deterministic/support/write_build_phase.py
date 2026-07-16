#!/usr/bin/env python3
import json
import sys
from pathlib import Path

out, build_ok, start_ok, message = Path(sys.argv[1]), sys.argv[2] == "true", sys.argv[3] == "true", sys.argv[4]
passed = build_ok and start_ok
payload = {
    "rubrics": [
        {
            "id": "a2m_build_runtime",
            "name": "I1 服务可构建启动",
            "dimension": "functionality",
            "type": "deterministic",
            "passed": passed,
            "score": 1.0 if passed else 0.0,
            "max_score": 1.0,
            "message": "install + build + start succeeded; GET /api/recipes returned 200" if passed else message,
            "evidence": ["install.log", "build.log", "server.log"],
        }
    ],
    "metadata": {"phase": "build", "build_ok": build_ok, "start_ok": start_ok},
}
out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
