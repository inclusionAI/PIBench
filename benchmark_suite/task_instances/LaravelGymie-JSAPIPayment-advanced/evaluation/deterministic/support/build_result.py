"""Merge case-local result files into /output/result.json."""
import json
import os
import sys
from pathlib import Path

OUTPUT_DIR = Path(sys.argv[1]) if len(sys.argv) > 1 else Path('/output')
SOURCES = ['static_checks.json', 'integration_results.json']


def load_json(name, default):
    try:
        with open(OUTPUT_DIR / name, encoding='utf-8') as f:
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

    infra = load_json('infra_failure.json', None)
    usage = load_json('agent_usage.json', {'usage_available': False})

    patch_path = OUTPUT_DIR / 'patch.diff'
    changed_path = OUTPUT_DIR / 'changed_files.txt'
    agent_output_path = OUTPUT_DIR / 'agent_output.txt'
    patch_empty = (not patch_path.exists()) or patch_path.stat().st_size == 0
    changed_empty = (not changed_path.exists()) or changed_path.stat().st_size == 0
    agent_output = ''
    try:
        agent_output = agent_output_path.read_text(encoding='utf-8', errors='ignore')
    except OSError:
        pass
    timeout_without_patch = bool(
        ('TIMEOUT: Agent did not produce output' in agent_output or 'Agent did not produce output' in agent_output)
        and patch_empty and changed_empty
    )
    refusal_without_patch = bool(
        patch_empty and changed_empty and (
            'usage policy' in agent_output.lower()
            or 'unable to respond to this request' in agent_output.lower()
            or 'cannot comply' in agent_output.lower()
            or 'policy refusal' in agent_output.lower()
        )
    )
    no_op_submission = (not infra) and patch_empty and changed_empty
    if no_op_submission:
        for item in rubrics:
            item['passed'] = False
            item['score'] = 0
            item['message'] = 'agent 未产出代码改动（no-op/timeout submission），不计入 baseline 自然得分'

    valid = [r for r in rubrics if not r.get('invalid')]
    passed = sum(1 for r in valid if r.get('passed'))
    total = len(valid)
    invalid_count = len(rubrics) - total
    score = round(passed / total, 4) if total else 0.0
    summary = '%d/%d passed' % (passed, total)
    if invalid_count:
        summary += ' (%d invalid rubric excluded)' % invalid_count
    retryable = bool(infra)
    if no_op_submission:
        if refusal_without_patch:
            summary = 'provider/agent refusal：agent 因策略拒答未产出代码改动，建议重试或单独标记为执行失败'
            retryable = True
        else:
            summary = 'agent 未产出代码改动（no-op/timeout submission），不计入 baseline 自然得分'
            retryable = timeout_without_patch
    if infra:
        summary = 'INFRA FAILURE: %s | %s' % (infra.get('reason', 'unknown'), summary)
        retryable = True
    if missing_sources:
        summary += ' | missing result files: %s' % ','.join(missing_sources)

    result = {
        'version': '1.0',
        'score': score,
        'max_score': 1.0,
        'summary': summary,
        'rubrics': rubrics,
        'agent': usage,
        'metadata': {
            'case': os.environ.get('PAYSKILLS_CASE_NAME', 'LaravelGymie-JSAPIPayment-advanced'),
            'raw_score': passed,
            'raw_max_score': total,
            'invalid_rubrics': invalid_count,
            'missing_result_sources': missing_sources,
            'retryable_infra_failure': retryable,
            'infra_failure': infra,
            'patch_empty': patch_empty,
            'changed_files_empty': changed_empty,
            'no_op_submission': no_op_submission,
            'timeout_without_patch': timeout_without_patch,
            'refusal_without_patch': refusal_without_patch,
        },
    }
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_DIR / 'result.json', 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print('result.json written: score=%s (%s)' % (score, summary))


if __name__ == '__main__':
    main()
