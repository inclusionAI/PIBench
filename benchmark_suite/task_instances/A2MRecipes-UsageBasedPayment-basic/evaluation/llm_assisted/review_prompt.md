你是代码评审员。下面是一个编码任务的 diff：开发者需要在 Next.js 食谱服务上接入支付验证，保护 GET /api/recipes/:id 付费资源（402 challenge、Payment-Proof 服务端验证、交付后向网关履约确认、fail-closed）。

请依据 diff 证据、hard integration evidence 和 agent_evidence.json 逐条判断以下审查点。hard integration evidence 是实际 HTTP/mock 网关运行证据；如果它证明有效 proof 无法释放资源、没有调用 verify 或没有履约确认，不要只因为 diff 中出现了相关代码片段就判通过。

{{RUBRIC_LINES}}

输出严格 JSON（不要 markdown 代码块），格式：
{"verdicts": [{"id": "<rubric id>", "passed": true, "reason": "一句话中文理由，引用具体代码证据"}]}

Hard integration evidence（可能为空）：
{{HARD_EVIDENCE}}

Agent evidence JSON（调用链与可见输出）：
{{AGENT_EVIDENCE_JSON}}

代码 diff（可能截断）：
```diff
{{DIFF}}
```
