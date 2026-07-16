你是一名资深支付安全代码评审员。请审查 Bill Express 线下收银台支付宝接入代码。

只根据给出的代码证据判断，不要因为具体 SDK、函数名、表名或 UI 文案不同而扣分；如果证据不足，判 false 并说明缺什么。不要过度思考；请直接给出最终 JSON，reason 保持简短。

对于 basic 用例，LLM judge 只评价支付产品形态和最终成功判定的设计语义；不要评价服务是否真实启动、接口是否真实可调用、二维码是否实际生成或网关调用是否成功，这些由 integration/e2e deterministic evaluation 负责。

审查项：
{{CHECKS_TEXT}}

必须输出严格 JSON，不要 markdown。格式如下，键必须完整：
{
{{JSON_SCHEMA}}
}
每个键的值必须是 {"passed": true/false, "reason": "..."}。

代码证据：
{{CODE_CONTEXT}}

Agent compact evidence:
```json
{{AGENT_EVIDENCE_JSON}}
```
