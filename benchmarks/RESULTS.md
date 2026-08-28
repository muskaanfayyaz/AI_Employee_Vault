# Token Optimization Benchmark Report

## Question

Can task-aware context selection reduce the input-token cost of the AI Employee Vault while preserving coding-agent task success?

## Baseline

The baseline sends all eligible repository context.

## Optimization

The experimental strategy ranks files using task/query relevance and sends only the most relevant files plus authoritative agent instructions.

## Results

Run:

`python benchmarks/token_cost_benchmark.py --repo . --json benchmark-results.json`

Paste the generated values here.

## Interpretation

Do not claim production savings from this experiment alone. It measures context size. A complete coding-agent evaluation should also compare task success, tests passed, latency, and output tokens.

## Evidence

Repository:
https://github.com/muskaanfayyaz/AI_Employee_Vault

Relevant existing architecture:

- persistent vault state machine
- structured prompt history
- separate agent skills
- authoritative `CLAUDE.md`
- task metadata and audit logs

These are the existing design elements this benchmark builds on.
