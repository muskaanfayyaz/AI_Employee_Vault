#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import os
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


DEFAULT_EXTS = {
    ".py", ".ts", ".tsx", ".js", ".jsx",
    ".md", ".json", ".yaml", ".yml",
    ".txt", ".toml", ".ini", ".cfg",
}

EXCLUDE_DIRS = {
    ".git", ".venv", "venv", "node_modules",
    "__pycache__", ".next", "dist", "build",
    ".pytest_cache", ".mypy_cache",
}

STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "into",
    "are", "was", "were", "will", "would", "should", "could",
    "have", "has", "had", "your", "you", "our", "their", "its",
    "about", "using", "use", "used", "code", "file", "files",
    "agent", "system", "project",
}

TASKS = [
    "retry reliability",
    "approval safety",
    "self improvement",
    "context optimization",
]


@dataclass
class Document:
    path: Path
    rel_path: str
    text: str
    tokens: int = 0


def tokenize_words(text: str) -> list[str]:
    return [
        word.lower()
        for word in re.findall(r"[A-Za-z_][A-Za-z0-9_/-]*", text)
        if len(word) > 2 and word.lower() not in STOPWORDS
    ]


def estimate_tokens(text: str) -> int:
    """Offline fallback estimate: approximately 4 characters per token."""
    return max(1, math.ceil(len(text) / 4))


def get_gemini_counter(repo: Path):
    """
    Return a function that counts tokens using Gemini's count_tokens API.

    The API key is loaded from <repo>/.env.
    Optional environment variable:
        GEMINI_MODEL=gemini-2.5-flash
    """

    try:
        from google import genai
    except ImportError:
        return None

    load_dotenv(repo / ".env")

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return None

    model = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")
    client = genai.Client(api_key=api_key)

    def count(text: str) -> int:
        response = client.models.count_tokens(
            model=model,
            contents=text,
        )
        return int(response.total_tokens)

    return count


def read_documents(repo: Path) -> list[Document]:
    documents: list[Document] = []

    for path in repo.rglob("*"):
        if not path.is_file():
            continue

        if any(part in EXCLUDE_DIRS for part in path.parts):
            continue

        if path.suffix.lower() not in DEFAULT_EXTS:
            continue

        # Exclude generated benchmark artifacts so previous results cannot
        # contaminate the context-selection experiment.
        if path.name.startswith("benchmark-results") and path.suffix.lower() == ".json":
            continue

        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue

        if not text.strip():
            continue

        documents.append(
            Document(
                path=path,
                rel_path=str(path.relative_to(repo)),
                text=text,
            )
        )

    return documents


def score_document(task: str, document: Document) -> float:
    """
    Simple lexical relevance score.

    This benchmark intentionally uses a transparent heuristic so the context
    selection method is reproducible and easy to inspect.
    """
    task_words = tokenize_words(task)
    if not task_words:
        return 0.0

    haystack = (
        document.rel_path.lower()
        + "\n"
        + document.text.lower()
    )

    score = 0.0

    for word in task_words:
        count = haystack.count(word)
        if count:
            score += min(count, 10) * 5.0

        if word in document.rel_path.lower():
            score += 10.0

    path_words = tokenize_words(document.rel_path)
    overlap = set(task_words) & set(path_words)
    score += len(overlap) * 5.0

    return score


def rank_documents(
    task: str,
    documents: list[Document],
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

    return ranked


def select_context(
    task: str,
    documents: list[Document],
    broad_k: int,
    top_k: int,
) -> list[tuple[float, Document]]:
    """
    Stage 1: retrieve a broader candidate set.
    Stage 2: keep the best top_k files.

    broad_k is retained for experimentation and future reranking extensions.
    """
    ranked = rank_documents(task, documents)
    candidates = ranked[:max(broad_k, top_k)]
    return candidates[:top_k]


def count_documents(
    documents: list[Document],
    counter,
) -> int:
    """
    Count tokens per file.

    Gemini API calls are cached in Document.tokens during one benchmark run.
    """
    total = 0

    for document in documents:
        if counter is not None:
            document.tokens = counter(document.text)
        else:
            document.tokens = estimate_tokens(document.text)

        total += document.tokens

    return total


def format_percent(value: float) -> str:
    text = f"{value:.2f}".rstrip("0").rstrip(".")
    return text


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Benchmark full-repository context against relevance-selected "
            "context for coding-agent token cost experiments."
        )
    )

    parser.add_argument(
        "--repo",
        default=".",
        help="Repository root to scan.",
    )

    parser.add_argument(
        "--top-k",
        type=int,
        default=8,
        help="Number of selected files per task.",
    )

    parser.add_argument(
        "--broad-k",
        type=int,
        default=25,
        help="Number of candidate files considered before top-k selection.",
    )

    parser.add_argument(
        "--tokenizer",
        choices=["estimate", "gemini"],
        default="estimate",
        help=(
            "Token counting method. "
            "'gemini' uses Gemini count_tokens and loads GEMINI_API_KEY "
            "from <repo>/.env."
        ),
    )

    parser.add_argument(
        "--json",
        dest="json_path",
        default=None,
        help="Optional path for a JSON benchmark report.",
    )

    args = parser.parse_args()

    if args.top_k <= 0:
        raise SystemExit("--top-k must be greater than 0.")

    if args.broad_k <= 0:
        raise SystemExit("--broad-k must be greater than 0.")

    repo = Path(args.repo).resolve()

    if not repo.exists() or not repo.is_dir():
        raise SystemExit(f"Repository not found: {repo}")

    counter = None
    tokenizer_label = "offline estimate (~4 chars/token)"
    tokenizer_name = "offline_estimate"

    if args.tokenizer == "gemini":
        counter = get_gemini_counter(repo)

        if counter is None:
            raise SystemExit(
                "Gemini tokenizer requested, but google-genai or python-dotenv "
                "is not installed, or GEMINI_API_KEY is missing from "
                f"{repo / '.env'}."
            )

        tokenizer_label = "Gemini API count_tokens"
        tokenizer_name = "gemini_api_count_tokens"

    documents = read_documents(repo)

    if not documents:
        raise SystemExit("No supported documents were found.")

    baseline_tokens = count_documents(documents, counter)

    print(f"Repository: {repo}")
    print(f"Documents scanned: {len(documents)}")
    print(f"Tokenizer: {tokenizer_label}")
    print()

    results = []

    for task in TASKS:
        selected = select_context(
            task=task,
            documents=documents,
            broad_k=args.broad_k,
            top_k=args.top_k,
        )

        optimized_tokens = sum(
            document.tokens
            for _, document in selected
        )

        saved_tokens = baseline_tokens - optimized_tokens
        saved_percent = (
            (saved_tokens / baseline_tokens) * 100
            if baseline_tokens
            else 0.0
        )

        result = {
            "task": task,
            "baseline_tokens": baseline_tokens,
            "baseline_files": len(documents),
            "optimized_tokens": optimized_tokens,
            "optimized_files": len(selected),
            "saved_tokens": saved_tokens,
            "saved_percent": round(saved_percent, 2),
            "selected": [
                {
                    "path": document.rel_path,
                    "score": round(score, 2),
                    "tokens": document.tokens,
                }
                for score, document in selected
            ],
        }

        results.append(result)

        print(f"Task: {task}")
        print(
            f"  baseline:  {baseline_tokens:,} tokens "
            f"across {len(documents)} files"
        )
        print(
            f"  optimized: {optimized_tokens:,} tokens "
            f"across {len(selected)} files"
        )
        print(
            f"  saved:     {saved_tokens:,} tokens "
            f"({format_percent(saved_percent)}%)"
        )
        print("  selected:")

        for score, document in selected:
            print(
                f"    - {document.rel_path} "
                f"(score={score:.1f}, tokens={document.tokens:,})"
            )

        print()

    average_saved_percent = (
        sum(item["saved_percent"] for item in results) / len(results)
        if results
        else 0.0
    )

    print("Summary")
    print(
        f"  average token reduction across tasks: "
        f"{format_percent(average_saved_percent)}%"
    )
    print()
    print(
        "Note: This benchmark measures context-token reduction. "
        "It does not by itself prove equal task quality or task success. "
        "A stronger benchmark should pair this with task-success evaluation."
    )

    report = {
        "repository": str(repo),
        "documents_scanned": len(documents),
        "tokenizer": tokenizer_name,
        "model": (
            os.getenv("GEMINI_MODEL", "gemini-3.6-flash")
            if args.tokenizer == "gemini"
            else None
        ),
        "broad_k": args.broad_k,
        "top_k": args.top_k,
        "average_saved_percent": round(average_saved_percent, 2),
        "results": results,
        "limitations": [
            "Measures context-token reduction only.",
            "Does not prove equal task quality or task success.",
            "Document ranking uses a transparent lexical relevance heuristic.",
        ],
    }

    if args.json_path:
        output_path = Path(args.json_path)

        if not output_path.is_absolute():
            output_path = Path.cwd() / output_path

        output_path.write_text(
            json.dumps(report, indent=2),
            encoding="utf-8",
        )

        print()
        print(f"JSON report written to: {output_path}")


if __name__ == "__main__":
    main()
