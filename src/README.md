# PaySkills Runtime Kit

This directory is the small execution kit vendored into every exported
benchmark suite. It is also the runtime boundary used by the web platform.

Most users only need the exported package root:

```bash
./run.sh --doctor
./run.sh --dry-run
./run.sh
```

The helper CLIs in `bin/` are stable entry points:

- `payskills-run`: unified runner for exported runs and web platform task instances.
- `payskills-agent`: drives Claude Code, OpenClaw, or Hermes and records traces.
- `payskills-judge`: calls an OpenAI-compatible LLM judge endpoint.
- `payskills-diff`: initializes and exports workspace diffs.
- `payskills-result`: validates, composes, or writes fallback `result.json`.

`payskills_runtime/` is the Python implementation behind those CLIs. It is
internal to the kit; benchmark authors and open-source users should normally
interact with the CLIs instead of importing Python modules directly.

## Exported Package Shape

An exported benchmark suite is expected to look like this:

```text
benchmark_suite/
kit/
config.yaml
config.example.yaml
.env.example
run.sh
README.md
runs/
```

The exported `run.sh` loads `.env`, reads `config.yaml`, and calls
`kit/bin/payskills-run`.

The web platform calls `payskills-run platform-task-instance ...` through the
same kit boundary.

## Runtime Contract

Each task instance runs through the same phases:

1. prepare workspace from `task/fixtures/project` when present
2. initialize a git baseline
3. run `task/run.sh`
4. export `artifacts/patch.diff`, `artifacts/changed_files.txt`, and
   `artifacts/code_files/`
5. run `evaluation/evaluate.sh`
6. validate or fallback `result.json`
7. write `execution.json` and run summaries

Standard outputs:

```text
result.json
execution.json
logs/
artifacts/
  patch.diff
  changed_files.txt
  code_files/
  agent_trace.json
  agent_events.jsonl
  agent_evidence.json
```

## Docker Mode

When `docker.enabled: true`, the kit builds the task instance image from
`task/Dockerfile`, layers in the selected agent runtime when needed, and runs the
same task-instance core inside the container with these mounts:

- `/task_instance`
- `/workspace`
- `/output`
- `/opt/payskills_runtime`

Task images must provide `bash`, `python3`, and `git`.

## Internal Layout

The Python runtime is grouped by responsibility:

- `agent/`: agent adapters, prompts, events, usage, evidence, and trace files
- `task_instance/`: task discovery, contract validation, and per-task execution
- `execution/`: run orchestration, `payskills_runtime.execution.preflight`,
  workspace, logs, and summaries
- `docker/`: Docker command construction, image build, and host execution
- `judge/`: LLM judge CLI and HTTP transport
- `result/`: result contract and weighted scoring composition
- `config/`: exported config parsing, defaults, validation, and summaries
- `doctor/`: `--doctor` checks and user-facing hints
- `export/`: self-contained package export and integrity checks
- `platform/`: web platform entry and sandbox backend
- `common/`: shared manifest and benchmark suite metadata helpers

See `payskills_runtime/README.md` for maintainer-level details.
