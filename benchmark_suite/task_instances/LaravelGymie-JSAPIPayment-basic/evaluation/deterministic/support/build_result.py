"""Merge all rubric result files into the final normalized /output/result.json."""
import json
import os
import sys

OUTPUT_DIR = sys.argv[1] if len(sys.argv) > 1 else "/output"

SOURCES = ["static_checks.json", "integration_results.json", "miniapp_checks.json", "llm_judge.json"]


def load_json(name, default):
    try:
        with open(os.path.join(OUTPUT_DIR, name)) as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def main():
    rubrics = []
    missing_sources = []
    for name in SOURCES:
        items = load_json(name, None)
        if items is None:
            missing_sources.append(name)
        elif isinstance(items, list):
            rubrics.extend(items)

    infra = load_json("infra_failure.json", None)
    usage = load_json("agent_usage.json", {"usage_available": False})

    patch_path = os.path.join(OUTPUT_DIR, "patch.diff")
    changed_path = os.path.join(OUTPUT_DIR, "changed_files.txt")
    agent_output_path = os.path.join(OUTPUT_DIR, "agent_output.txt")
    patch_empty = (not os.path.exists(patch_path)) or os.path.getsize(patch_path) == 0
    changed_empty = (not os.path.exists(changed_path)) or os.path.getsize(changed_path) == 0
    agent_output = ""
    try:
        with open(agent_output_path, encoding="utf-8", errors="ignore") as f:
            agent_output = f.read()
    except OSError:
        pass
    timeout_without_patch = bool(
        ("TIMEOUT: Agent did not produce output" in agent_output
         or "Agent did not produce output" in agent_output)
        and patch_empty and changed_empty
    )
    no_op_submission = (not infra) and patch_empty and changed_empty
    if no_op_submission:
        for item in rubrics:
            item["passed"] = False
            item["score"] = 0
            item["message"] = "agent 未产出代码改动（no-op/timeout submission），不计入 baseline 自然得分"

    invalid_count = sum(1 for r in rubrics if r.get("invalid"))
    for r in rubrics:
        if r.get("invalid"):
            r["invalid"] = False
            r["passed"] = False
            r["score"] = 0
            r["message"] = (r.get("message", "") + "；" if r.get("message") else "") + "invalid result counted as failed"
    passed = sum(1 for r in rubrics if r.get("passed"))
    total = len(rubrics)
    score = round(passed / total, 4) if total else 0.0

    summary = "%d/%d passed" % (passed, total)
    if invalid_count:
        summary += " (%d invalid rubric counted as failed)" % invalid_count

    llm_judge_infra_failure = os.path.exists(os.path.join(OUTPUT_DIR, "llm_judge_infra_failure.json"))
    retryable = bool(llm_judge_infra_failure)
    if no_op_submission:
        summary = "agent 未产出代码改动（no-op/timeout submission），不计入 baseline 自然得分"
        retryable = timeout_without_patch
    if infra:
        retryable = True
        summary = "INFRA FAILURE: %s | %s" % (infra.get("reason", "unknown"), summary)
    if missing_sources:
        summary += " | missing result files: %s" % ",".join(missing_sources)
    if llm_judge_infra_failure:
        summary += " | LLM judge infra failure, rerun required"

    result = {
        "version": "1.0",
        "score": score,
        "max_score": 1.0,
        "summary": summary,
        "rubrics": rubrics,
        "agent": usage,
        "metadata": {
            "raw_score": passed,
            "raw_max_score": total,
            "invalid_rubrics": invalid_count,
            "missing_result_sources": missing_sources,
            "retryable_infra_failure": retryable,
            "llm_judge_infra_failure": llm_judge_infra_failure,
            "infra_failure": infra,
            "patch_empty": patch_empty,
            "changed_files_empty": changed_empty,
            "no_op_submission": no_op_submission,
            "timeout_without_patch": timeout_without_patch,
        },
    }
    with open(os.path.join(OUTPUT_DIR, "result.json"), "w") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print("result.json written: score=%s (%s)" % (score, summary))


if __name__ == "__main__":
    main()
