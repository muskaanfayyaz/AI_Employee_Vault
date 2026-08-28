# AI Employee Vault — Token Optimization Benchmark

This benchmark is designed specifically around the token-cost question from a coding-agent evaluation.

## What it tests

It compares two context strategies for the same coding task:

1. Baseline: send all eligible repository text to the model.
2. Optimized: rank repository files by task relevance and send only the top relevant files plus authoritative agent instructions.

The benchmark reports:

- baseline input tokens
- optimized input tokens
- tokens saved
- percentage reduction
- number of files sent
- exact files selected

## Why this is relevant to AI Employee Vault

The existing project already has a strong foundation for context engineering:

- `CLAUDE.md` defines the coding-agent operating rules.
- The vault is a persistent state machine rather than a conversation transcript.
- `history/prompts/` stores structured prompt history.
- `src/skills/` separates agent responsibilities.
- Vault items carry structured YAML metadata such as status, priority, classification and timestamps.

These characteristics make it possible to evaluate a task-aware context-selection layer without rewriting the whole system.

## Run

From the repository root:

```bash
python benchmarks/token_cost_benchmark.py --repo .
```

For provider-native Claude token counting:

```bash
pip install anthropic
```

Set `ANTHROPIC_API_KEY`, then:

```bash
python benchmarks/token_cost_benchmark.py --repo . --tokenizer anthropic --json benchmark-results.json
```

## Important honesty rule

Do not report the benchmark as an historical result from the original AI Employee Vault.

It is a new experiment performed on the existing codebase.

If the optimized strategy has not yet been used in production, describe it as:

"An experimental context-selection benchmark built on my AI Employee Vault codebase."

Do not claim a percentage until you run the benchmark.

## Stronger evaluation

For a stronger coding-agent benchmark, run the same 3–4 coding tasks under both strategies and record:

| Metric | Baseline | Optimized |
|---|---:|---:|
| Input tokens | measured | measured |
| Output tokens | measured | measured |
| Total tokens | measured | measured |
| Estimated input cost | measured | measured |
| Latency | measured | measured |
| Task success | measured | measured |
| Tests passed | measured | measured |

The key result is not "fewer tokens" alone. The strongest result is:

"X% fewer input tokens with no loss in task success."

That directly addresses the trade-off Harendra is asking about.
