#!/usr/bin/env python3
"""
Coding-agent token optimization benchmark.

Compares:
1. Full repository context
2. Relevance-selected context

using Gemini's count_tokens API.

This benchmark is intentionally conservative:
- It does NOT claim token reduction equals task success.
- It measures the actual Gemini token count of each context.
- It evaluates whether selected context contains the files needed
  for each predefined coding task.
"""

from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv
from google import genai


DEFAULT_EXTS = {
    ".py", ".ts", ".tsx", ".js", ".jsx",
    ".md", ".json", ".yaml", ".yml",
    ".txt", ".toml", ".ini", ".cfg",
}

EXCLUDE_DIRS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".next",
    "dist",
    "build",
    ".pytest_cache",
    ".mypy_cache",
}

STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "into",
    "are", "was", "were", "will", "would", "should", "could",
    "have", "has", "had", "your", "you", "our", "their", "its",
    "about", "using", "use", "used", "code", "file", "files",
    "agent", "system", "project",
}


@dataclass
class Document:
    path: Path
    rel_path: str
    text: str
    tokens: int = 0


@dataclass
class Task:
    name: str
    prompt: str
    expected_files: list[str]


TASKS = [
    Task(
        name="retry reliability",
        prompt=(
            "You are working on this repository's coding agent. "
            "Investigate the retry mechanism and explain how you would "
            "improve retry reliability, failure recovery, and backoff behavior. "
            "Identify the relevant implementation and tests, then propose "
            "a concrete code-level change."
        ),
        expected_files=[
            "src/engine/retry.py",
            "tests/unit/test_retry.py",
        ],
    ),
    Task(
        name="approval safety",
        prompt=(
            "You are working on this repository's coding agent. "
            "Investigate the approval workflow and explain how you would "
            "prevent unsafe irreversible actions while preserving useful "
            "automation. Identify the relevant implementation, policy, "
            "and tests, then propose a concrete code-level improvement."
        ),
        expected_files=[
            "src/approval/manager.py",
            "src/models/approval.py",
            "Config/approval_policy.yaml",
            "tests/unit/test_approval_manager.py",
        ],
    ),
    Task(
        name="context optimization",
        prompt=(
            "You are optimizing a coding agent's context window. "
            "Given this repository, determine which files are actually "
            "necessary to answer a coding question about context selection "
            "and token reduction. Explain how irrelevant context can be "
            "removed while retaining the information needed for reliable "
            "coding decisions. Propose a concrete retrieval or context "
            "optimization strategy."
        ),
        expected_files=[
            "benchmarks/token_cost_benchmark.py",
            "README.md",
        ],
    ),
]


def tokenize_words(text: str) -> list[str]:
    return [
        word.lower()
        for word in re.findall(
            r"[A-Za-z_][A-Za-z0-9_/-]*",
            text,
        )
    ]


def load_repository(repo: Path) -> list[Document]:
    documents: list[Document] = []

    for path in repo.rglob("*"):
        if not path.is_file():
            continue

        if any(part in EXCLUDE_DIRS for part in path.parts):
            continue

        if path.suffix.lower() not in DEFAULT_EXTS:
            continue

        # Never include secrets.
        if path.name in {".env", ".env.local", ".env.production"}:
            continue

        # Never let previous benchmark output contaminate retrieval.
        if (
            path.name.startswith("benchmark-results")
            and path.suffix.lower() == ".json"
        ):
            continue

        try:
            text = path.read_text(
                encoding="utf-8",
                errors="ignore",
            )
        except OSError:
            continue

        if not text.strip():
            continue

        documents.append(
            Document(
                path=path,
                rel_path=str(path.relative_to(repo)).replace("\\", "/"),
                text=text,
            )
        )

    return documents


def score_document(task: str, document: Document) -> float:
    task_words = [
        word
        for word in tokenize_words(task)
        if word not in STOPWORDS
    ]

    if not task_words:
        return 0.0

    path_text = document.rel_path.lower()
    body_text = document.text.lower()

    score = 0.0

    for word in task_words:
        body_count = body_text.count(word)

        if body_count:
            score += min(body_count, 10) * 5.0

        if word in path_text:
            score += 10.0

    path_words = set(tokenize_words(document.rel_path))
    overlap = set(task_words) & path_words
    score += len(overlap) * 5.0

    return score


def select_context(
    task: str,
    documents: list[Document],
    top_k: int,
) -> list[tuple[float, Document]]:
    ranked = [
        (score_document(task, document), document)
        for document in documents
    ]

    ranked.sort(
        key=lambda item: (
            item[0],
            -item[1].tokens,
            item[1].rel_path,
        ),
        reverse=True,
    )

    return ranked[:top_k]


def get_gemini_counter(repo: Path):
    env_path = repo / ".env"

    if env_path.exists():
        load_dotenv(env_path)

    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        raise RuntimeError(
            f"GEMINI_API_KEY was not found in {env_path}"
        )

    model = os.getenv(
        "GEMINI_MODEL",
        "gemini-3.6-flash",
    )

    client = genai.Client(api_key=api_key)

    def count(text: str) -> int:
        response = client.models.count_tokens(
            model=model,
            contents=text,
        )
        return int(response.total_tokens)

    return count, model


def build_context(
    documents: list[Document],
) -> str:
    chunks: list[str] = []

    for document in documents:
        chunks.append(
            "\n".join(
                [
                    f"===== FILE: {document.rel_path} =====",
                    document.text,
                    f"===== END FILE: {document.rel_path} =====",
                ]
            )
        )

    return "\n\n".join(chunks)


def normalize_path(path: str) -> str:
    return path.replace("\\", "/").lower()


def evaluate_file_coverage(
    selected: list[tuple[float, Document]],
    expected_files: list[str],
) -> dict:
    selected_paths = {
        normalize_path(document.rel_path)
        for _, document in selected
    }

    expected = {
        normalize_path(path)
        for path in expected_files
    }

    matched = sorted(selected_paths & expected)
    missing = sorted(expected - selected_paths)

    coverage = (
        len(matched) / len(expected)
        if expected
        else 1.0
    )

    return {
        "expected_files": sorted(expected),
        "matched_files": matched,
        "missing_files": missing,
        "coverage": round(coverage, 4),
    }


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--repo",
        default="..",
        help="Repository root",
    )

    parser.add_argument(
        "--top-k",
        type=int,
        default=8,
        help="Number of files selected for optimized context",
    )

    parser.add_argument(
        "--json",
        dest="json_path",
        default="coding-agent-results.json",
        help="Output JSON file",
    )

    args = parser.parse_args()

    repo = Path(args.repo).resolve()

    if not repo.exists():
        raise SystemExit(f"Repository does not exist: {repo}")

    counter, model = get_gemini_counter(repo)

    documents = load_repository(repo)

    print(f"Repository: {repo}")
    print(f"Documents scanned: {len(documents)}")
    print(f"Tokenizer: Gemini API count_tokens")
    print(f"Model: {model}")
    print()

    print("Counting repository baseline tokens...")

    baseline_tokens = 0

    for document in documents:
        document.tokens = counter(document.text)
        baseline_tokens += document.tokens

    print(f"Full repository tokens: {baseline_tokens:,}")
    print()

    results = []

    for task in TASKS:
        selected = select_context(
            task.prompt,
            documents,
            args.top_k,
        )

        selected_documents = [
            document
            for _, document in selected
        ]

        optimized_context = build_context(
            selected_documents
        )

        optimized_tokens = counter(
            optimized_context
        )

        reduction = (
            (baseline_tokens - optimized_tokens)
            / baseline_tokens
            * 100
            if baseline_tokens
            else 0
        )

        coverage = evaluate_file_coverage(
            selected,
            task.expected_files,
        )

        print(f"Task: {task.name}")
        print(
            f"  baseline:  {baseline_tokens:,} tokens"
        )
        print(
            f"  optimized: {optimized_tokens:,} tokens"
        )
        print(
            f"  saved:     "
            f"{baseline_tokens - optimized_tokens:,} tokens "
            f"({reduction:.2f}%)"
        )
        print(
            f"  expected-file coverage: "
            f"{coverage['coverage'] * 100:.1f}%"
        )

        print("  selected:")

        for score, document in selected:
            print(
                f"    - {document.rel_path} "
                f"(score={score:.1f}, tokens={document.tokens:,})"
            )

        print("  missing expected files:")

        if coverage["missing_files"]:
            for path in coverage["missing_files"]:
                print(f"    - {path}")
        else:
            print("    none")

        print()

        results.append(
            {
                "task": task.name,
                "prompt": task.prompt,
                "baseline_tokens": baseline_tokens,
                "optimized_tokens": optimized_tokens,
                "tokens_saved": (
                    baseline_tokens - optimized_tokens
                ),
                "reduction_percent": round(
                    reduction,
                    2,
                ),
                "top_k": args.top_k,
                "selected_files": [
                    {
                        "path": document.rel_path,
                        "score": score,
                        "tokens": document.tokens,
                    }
                    for score, document in selected
                ],
                "coverage": coverage,
            }
        )

    average_reduction = (
        sum(
            result["reduction_percent"]
            for result in results
        )
        / len(results)
        if results
        else 0
    )

    average_coverage = (
        sum(
            result["coverage"]["coverage"]
            for result in results
        )
        / len(results)
        if results
        else 0
    )

    report = {
        "benchmark": "coding-agent-context-optimization",
        "version": 1,
        "repository": str(repo),
        "documents_scanned": len(documents),
        "tokenizer": "Gemini API count_tokens",
        "model": model,
        "top_k": args.top_k,
        "baseline_tokens": baseline_tokens,
        "average_reduction_percent": round(
            average_reduction,
            2,
        ),
        "average_expected_file_coverage": round(
            average_coverage,
            4,
        ),
        "tasks": results,
        "limitations": [
            "Token reduction alone does not prove equal task quality.",
            "Expected-file coverage is a structural proxy, not a task-success metric.",
            "The retrieval method is a transparent lexical heuristic.",
            "A stronger evaluation should compare actual coding-agent outputs.",
        ],
    }

    output_path = Path(args.json_path)

    if not output_path.is_absolute():
        output_path = Path.cwd() / output_path

    output_path.write_text(
        json.dumps(
            report,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("Summary")
    print(
        f"  average token reduction: "
        f"{average_reduction:.2f}%"
    )
    print(
        f"  average expected-file coverage: "
        f"{average_coverage * 100:.1f}%"
    )
    print()
    print(
        f"JSON report written to: {output_path}"
    )


if __name__ == "__main__":
    main()