# payskills_runtime

This package is the internal implementation of the PaySkills runtime kit. The
public surface is the CLI set under `../bin/`; Python modules are organized by
domain so maintainers can find the right layer quickly.

```text
payskills_runtime/
  runner.py          # payskills-run command dispatch
  agent/             # agent CLI, provider adapters, events, usage, evidence
  task_instance/     # task discovery, contract checks, task execution
  execution/         # run orchestration, runtime inputs, preflight, output layout
  docker/            # Docker commands, host runner, image build helpers
  judge/             # payskills-judge CLI and transport
  result/            # result.json contract and scoring composition
  config/            # config.yaml parsing, defaults, contract checks
  doctor/            # doctor checks, output, and hints
  export/            # package export and layout validation
  platform/          # web-platform task instance entry and sandbox backend
  common/            # shared manifest and benchmark suite metadata helpers
```

## Main Flows

`payskills-run --export-root ...`

1. `runner.py`
2. `execution.preflight`
3. `execution.orchestrator`
4. `task_instance.runner`
5. `task_instance.execution`
6. `result` and `execution.summary`

`payskills-run platform-task-instance ...`

1. `runner.py`
2. `platform.task_instance`
3. `platform.sandbox`
4. `task_instance.execution`
5. `result` and `execution`

`payskills-agent drive-turns ...`

1. `agent.cli`
2. `agent.drive`
3. `agent.invocation`
4. `agent.providers`
5. `agent.events`, `agent.usage`, `agent.evidence`, and `agent.artifacts`

## Boundary Rules

- The kit must not import from `web/`.
- The web platform should call `bin/payskills-run` instead of importing kit
  internals.
- Task instances should call the helper CLIs (`payskills-agent`,
  `payskills-judge`, `payskills-result`, `payskills-diff`) rather than importing
  Python modules.
- Keep `runner.py` and the files under `../bin/` stable; they are the runtime
  entry points used by both exported packages and the web platform.
