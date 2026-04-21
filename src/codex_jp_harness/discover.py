"""Discover candidate banned terms from observed Codex output.

The fast-path auto-rewrite (v0.2.17) can only fix what's in
``banned_terms.yaml``; real dogfooding shows most leaked English nouns
(``preview``, ``review``, ``iframe``, ``composer``, ``harness``, …) are
project-specific and never make it into the bundled rule set.

This module gives the tuning skill a way to **surface candidate terms
from a pasted or file-provided Codex draft**, so the user can decide
which ones to add to their ``~/.codex/jp_lint.yaml`` user-local override
instead of waiting for an upstream PR.

The scanner is a pure function: take the text, the set of already-known
banned terms, and a standard-English allowlist, return a ranked list of
candidates with occurrence counts and representative context snippets.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from codex_jp_harness.rules import (
    _mask_markdown_links,
    _strip_code_blocks,
)

# Tokens matching this regex are considered candidate English nouns.
# Length ≥ 3 to avoid the noise of ``a``/``is``/``of`` etc.
_TOKEN_RE = re.compile(r"(?<![A-Za-z0-9_])([A-Za-z][A-Za-z]{2,})(?![A-Za-z0-9_-])")

# Words that look like English nouns but are widely understood in Japanese
# technical writing — flagging them would be noise. Kept lowercase for
# case-insensitive matching.
DEFAULT_ALLOWLIST: frozenset[str] = frozenset(
    {
        # protocols / formats
        "api",
        "http",
        "https",
        "url",
        "uri",
        "json",
        "yaml",
        "yml",
        "xml",
        "html",
        "css",
        "svg",
        "png",
        "jpg",
        "pdf",
        "csv",
        "tsv",
        "toml",
        "ini",
        # languages / runtimes
        "js",
        "ts",
        "py",
        "rs",
        "go",
        "java",
        "ruby",
        "python",
        "rust",
        "node",
        "deno",
        "bun",
        # process / tools
        "ci",
        "cd",
        "pr",
        "mcp",
        "sdk",
        "ide",
        "cli",
        "ssh",
        "ftp",
        "rpc",
        "grpc",
        "dns",
        "tls",
        "ssl",
        "oauth",
        "jwt",
        "vpn",
        "nat",
        "npm",
        "pip",
        "uv",
        "pnpm",
        "yarn",
        "git",
        "cmd",
        "pwsh",
        "bash",
        "zsh",
        "tui",
        "gui",
        # hardware / OS
        "cpu",
        "gpu",
        "ram",
        "rom",
        "ssd",
        "hdd",
        "usb",
        "pc",
        "os",
        "ios",
        "mac",
        "linux",
        "windows",
        # UI / AI surface
        "ui",
        "ux",
        "id",
        "ai",
        "ml",
        "llm",
        "rag",
        # HTTP verbs (kept case-insensitive)
        "get",
        "post",
        "put",
        "patch",
        "delete",
        # standard I/O streams / shell primitives (no clean Japanese equivalent)
        "stdin",
        "stdout",
        "stderr",
        # git verbs / nouns commonly kept in English (merge / rebase live in
        # banned_terms at lower severity, so no duplicates here)
        "commit",
        "push",
        "pull",
        "branch",
        "tag",
        "clone",
        "fork",
        "diff",
        "blame",
        "stash",
        # testing frameworks / tools that only exist as proper nouns
        "pester",
        "pytest",
        "jest",
        "mocha",
        "vitest",
        "rspec",
        "cargo",
        "rustc",
        # unix / shell tool names
        "grep",
        "awk",
        "sed",
        "curl",
        "wget",
        "jq",
        "ssh",
        "scp",
        "rsync",
        # proper nouns that should stay English
        "github",
        "openai",
        "anthropic",
        "claude",
        "codex",
        "voicevox",
        "obsidian",
    }
)


@dataclass
class Candidate:
    """A candidate English noun detected in the text."""

    term: str
    count: int
    contexts: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"term": self.term, "count": self.count, "contexts": list(self.contexts)}


def scan_text(
    text: str,
    existing_terms: set[str] | None = None,
    allowlist: set[str] | None = None,
    *,
    min_occurrences: int = 2,
    max_contexts: int = 3,
) -> list[Candidate]:
    """Return a ranked list of English-noun candidates found in ``text``.

    Args:
        text: The Codex draft to scan (plain text, possibly with fenced
            code blocks, inline backticks, and markdown links).
        existing_terms: Terms already in the user's effective banned list.
            Excluded from results. Case-insensitive compare.
        allowlist: Standard English acronyms/proper nouns to ignore. If
            None, ``DEFAULT_ALLOWLIST`` is used. Case-insensitive.
        min_occurrences: Minimum times a term must appear before it's
            surfaced. Defaults to 2 so one-off noise is filtered out.
        max_contexts: How many context snippets to store per candidate.

    Returns:
        Candidates ordered by count descending, then term alphabetical.
    """
    existing_ci = {t.lower() for t in (existing_terms or set())}
    allow_ci = {t.lower() for t in (allowlist or DEFAULT_ALLOWLIST)}

    # Strip fenced code blocks entirely; mask inline backticks and markdown
    # link URLs on each line so tokens inside them don't leak into results.
    scrubbed = _strip_code_blocks(text)
    lines = scrubbed.split("\n")

    counts: dict[str, int] = {}
    contexts: dict[str, list[str]] = {}

    for line in lines:
        masked = _mask_markdown_links(line)
        # Custom masking for inline backticks that keeps positions useful:
        # we don't need to preserve columns for discover, so simple drop is fine.
        masked = re.sub(r"`[^`]*`", " ", masked)

        for match in _TOKEN_RE.finditer(masked):
            token = match.group(1)
            key = token.lower()
            if key in existing_ci or key in allow_ci:
                continue
            counts[key] = counts.get(key, 0) + 1
            if counts[key] <= max_contexts:
                snippet = line.strip()
                if len(snippet) > 80:
                    # Keep a window around the match so the user sees the context.
                    start = max(0, match.start() - 25)
                    end = min(len(line), match.end() + 25)
                    snippet = ("…" if start > 0 else "") + line[start:end].strip() + (
                        "…" if end < len(line) else ""
                    )
                contexts.setdefault(key, []).append(snippet)

    candidates = [
        Candidate(term=term, count=c, contexts=contexts.get(term, []))
        for term, c in counts.items()
        if c >= min_occurrences
    ]
    candidates.sort(key=lambda c: (-c.count, c.term))
    return candidates


SUGGESTION_DICT: dict[str, str] = {
    "preview": "プレビュー、確認用",
    "review": "レビュー",
    "iframe": "インラインフレーム、埋め込み枠",
    "composer": "入力欄、編集エリア",
    "draft": "下書き",
    "overlay": "前面表示、重ねて表示",
    "context": "文脈、前提",
    "viewport": "表示領域",
    "footer": "下部帯",
    "header": "上部帯",
    "toolbar": "操作帯",
    "drawer": "引き出しパネル",
    "sheet": "シート、パネル",
    "harness": "検査基盤、足場",
    "chrome": "枠、装飾帯",
    "attribution": "帰属表示、出典表記",
    "remote": "リモート、遠隔",
    "upstream": "上流、参照元",
    "tracked": "追跡対象",
    "workspace": "作業領域",
    "terminal": "端末、ターミナル",
    "panel": "パネル",
    "surface": "面、表示面",
    "anchor": "錨、基準点",
    "checkpoint": "中間点、区切り",
    "layout": "配置",
    "session": "セッション",
    "pipeline": "パイプライン",
}


def suggest_for(term: str) -> str | None:
    """Return a suggested Japanese replacement for ``term`` if known."""
    return SUGGESTION_DICT.get(term.lower())
