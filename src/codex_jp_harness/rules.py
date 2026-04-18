"""Lint rules for Japanese technical report drafts.

Pure functions — no I/O except load_rules. All detection is via regex.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class Violation:
    """A single rule violation found in the draft."""

    rule: str
    line: int
    snippet: str = ""
    term: str = ""
    token: str = ""
    count: int = 0
    limit: int = 0
    suggest: str = ""
    fix: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return {k: v for k, v in d.items() if v not in ("", 0)}


@dataclass
class RuleConfig:
    banned: list[dict[str, str]] = field(default_factory=list)
    identifier_pattern: str = r"[A-Za-z_][A-Za-z0-9]*[._/-][A-Za-z0-9_./-]+"
    sentence_split_pattern: str = r"[。\n]"
    identifier_limit_per_sentence: int = 2
    sentence_length_enabled: bool = True
    sentence_max_chars: int = 80
    sentence_max_chars_with_identifiers: int = 50


def load_rules(yaml_path: Path) -> RuleConfig:
    """Load banned_terms.yaml into a RuleConfig."""
    with yaml_path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    length_cfg = raw.get("sentence_length", {}) or {}
    return RuleConfig(
        banned=raw.get("banned", []),
        identifier_pattern=raw.get("identifier_pattern", RuleConfig.identifier_pattern),
        sentence_split_pattern=raw.get(
            "sentence_split_pattern", RuleConfig.sentence_split_pattern
        ),
        identifier_limit_per_sentence=raw.get(
            "identifier_limit_per_sentence", RuleConfig.identifier_limit_per_sentence
        ),
        sentence_length_enabled=length_cfg.get(
            "enabled", RuleConfig.sentence_length_enabled
        ),
        sentence_max_chars=length_cfg.get("max_chars", RuleConfig.sentence_max_chars),
        sentence_max_chars_with_identifiers=length_cfg.get(
            "max_chars_with_identifiers",
            RuleConfig.sentence_max_chars_with_identifiers,
        ),
    )


def _strip_code_blocks(text: str) -> str:
    """Replace fenced code blocks with blank lines (preserve line numbers)."""

    def _blank(match: re.Match[str]) -> str:
        return "\n" * match.group().count("\n")

    return re.sub(r"```.*?```", _blank, text, flags=re.DOTALL)


def _mask_markdown_links(line: str) -> str:
    """Mask the URL portion of markdown links `[text](url)` with spaces.

    Without this, bare_identifier flags the URL inside the parentheses as a
    code identifier (URLs contain `.`, `/`, `-`).
    """
    return re.sub(
        r"(\[[^\]]*\])(\([^)]*\))",
        lambda m: m.group(1) + " " * len(m.group(2)),
        line,
    )


def _mask_inline_code(line: str) -> str:
    """Mask backtick-enclosed spans with spaces (preserve column positions)."""
    masked = _mask_markdown_links(line)
    return re.sub(r"`[^`]*`", lambda m: " " * len(m.group()), masked)


def detect_banned_terms(text: str, cfg: RuleConfig) -> list[Violation]:
    """Detect banned terms NOT enclosed in backticks or code blocks."""
    violations: list[Violation] = []
    scan = _strip_code_blocks(text)
    lines = scan.split("\n")

    for entry in cfg.banned:
        term = entry.get("term", "")
        if not term:
            continue
        suggest = entry.get("suggest", "")
        pattern = re.compile(
            r"(?<![A-Za-z0-9_])" + re.escape(term) + r"(?![A-Za-z0-9_-])",
            re.IGNORECASE,
        )
        for lineno, raw_line in enumerate(lines, 1):
            masked = _mask_inline_code(raw_line)
            if pattern.search(masked):
                violations.append(
                    Violation(
                        rule="banned_term",
                        line=lineno,
                        term=term,
                        snippet=raw_line.strip()[:100],
                        suggest=suggest,
                    )
                )
    return violations


def detect_bare_identifiers(text: str, cfg: RuleConfig) -> list[Violation]:
    """Detect code-like identifiers NOT wrapped in backticks."""
    violations: list[Violation] = []
    scan = _strip_code_blocks(text)
    lines = scan.split("\n")
    pattern = re.compile(cfg.identifier_pattern)

    for lineno, raw_line in enumerate(lines, 1):
        masked = _mask_inline_code(raw_line)
        for match in pattern.finditer(masked):
            violations.append(
                Violation(
                    rule="bare_identifier",
                    line=lineno,
                    token=match.group(),
                    snippet=raw_line.strip()[:100],
                    fix="バッククォートで囲む",
                )
            )
    return violations


def detect_too_many_identifiers(text: str, cfg: RuleConfig) -> list[Violation]:
    """Flag sentences containing more than `limit` code identifiers."""
    violations: list[Violation] = []
    scan = _strip_code_blocks(text)
    pattern = re.compile(cfg.identifier_pattern)
    splitter = re.compile(cfg.sentence_split_pattern)

    cursor = 0
    line = 1
    for sentence in splitter.split(scan):
        if sentence.strip():
            masked = _mask_inline_code(sentence)
            count = len(pattern.findall(masked))
            if count > cfg.identifier_limit_per_sentence:
                violations.append(
                    Violation(
                        rule="too_many_identifiers",
                        line=line + scan[:cursor].count("\n"),
                        count=count,
                        limit=cfg.identifier_limit_per_sentence,
                        snippet=sentence.strip()[:100],
                        fix="文を分割する",
                    )
                )
        cursor += len(sentence) + 1
    return violations


def detect_sentence_length(text: str, cfg: RuleConfig) -> list[Violation]:
    """Flag sentences that exceed the VOICEVOX-inspired length ceiling.

    Rationale: if a sentence cannot be spoken aloud in one breath, it is
    almost always packed too densely with identifiers or clauses. Sentences
    containing code identifiers get a stricter limit.
    """
    if not cfg.sentence_length_enabled:
        return []

    violations: list[Violation] = []
    scan = _strip_code_blocks(text)
    id_pattern = re.compile(cfg.identifier_pattern)
    splitter = re.compile(cfg.sentence_split_pattern)

    cursor = 0
    for sentence in splitter.split(scan):
        stripped = sentence.strip()
        if stripped:
            masked = _mask_inline_code(stripped)
            length = len(stripped)
            has_identifier = bool(id_pattern.search(masked))
            limit = (
                cfg.sentence_max_chars_with_identifiers
                if has_identifier
                else cfg.sentence_max_chars
            )
            if length > limit:
                line = 1 + scan[:cursor].count("\n")
                violations.append(
                    Violation(
                        rule="sentence_too_long",
                        line=line,
                        count=length,
                        limit=limit,
                        snippet=stripped[:100],
                        fix="文を分割する。音読して一息で読めないなら長すぎる。",
                    )
                )
        cursor += len(sentence) + 1
    return violations


def lint(text: str, cfg: RuleConfig) -> list[Violation]:
    """Run all enabled detection rules and return violations."""
    return (
        detect_banned_terms(text, cfg)
        + detect_bare_identifiers(text, cfg)
        + detect_too_many_identifiers(text, cfg)
        + detect_sentence_length(text, cfg)
    )
