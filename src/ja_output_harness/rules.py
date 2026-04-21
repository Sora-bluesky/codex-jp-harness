"""Lint rules for Japanese technical report drafts.

Pure functions — no I/O except load_rules. All detection is via regex.
"""

from __future__ import annotations

import os
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
    severity: str = "ERROR"
    category: str = ""

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


def resolve_user_config_path() -> Path:
    """Return the user-local override path (may not exist).

    Priority:
      1. $CODEX_JP_HARNESS_USER_CONFIG (absolute path)
      2. $XDG_CONFIG_HOME/ja-output-harness/jp_lint.yaml
      3. ~/.codex/jp_lint.yaml
    """
    env = os.environ.get("CODEX_JP_HARNESS_USER_CONFIG")
    if env:
        return Path(env).expanduser()
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg).expanduser() / "ja-output-harness" / "jp_lint.yaml"
    return Path.home() / ".codex" / "jp_lint.yaml"


def _apply_user_overrides(raw: dict[str, Any], user_raw: dict[str, Any]) -> dict[str, Any]:
    """Merge a user override dict into the bundled rules dict.

    Schema of user_raw:
      disable:    list of term strings to drop from banned
      overrides:  mapping {term: {severity, suggest, category, katakana_form}}
      add:        list of banned-entry dicts (same shape as bundled entries)
      thresholds: partial override for identifier_limit_per_sentence,
                  identifier_pattern, sentence_split_pattern, sentence_length
    """
    merged = dict(raw)
    banned = list(merged.get("banned", []) or [])

    disable = set(user_raw.get("disable", []) or [])
    if disable:
        banned = [e for e in banned if e.get("term") not in disable]

    add = user_raw.get("add", []) or []
    if add:
        banned.extend(e for e in add if isinstance(e, dict) and e.get("term"))

    # overrides は disable/add を反映した後に適用することで、user-added の
    # term にも set-severity が効くようにする（gpt-5.4 review #44）。
    overrides = user_raw.get("overrides", {}) or {}
    if overrides:
        for entry in banned:
            term = entry.get("term", "")
            if term in overrides and isinstance(overrides[term], dict):
                entry.update(overrides[term])

    merged["banned"] = banned

    thresholds = user_raw.get("thresholds", {}) or {}
    for key in ("identifier_pattern", "sentence_split_pattern", "identifier_limit_per_sentence"):
        if key in thresholds:
            merged[key] = thresholds[key]
    if "sentence_length" in thresholds and isinstance(thresholds["sentence_length"], dict):
        base_len = dict(merged.get("sentence_length", {}) or {})
        base_len.update(thresholds["sentence_length"])
        merged["sentence_length"] = base_len

    return merged


def load_rules(yaml_path: Path, user_yaml_path: Path | None = None) -> RuleConfig:
    """Load banned_terms.yaml into a RuleConfig.

    If ``user_yaml_path`` is given and the file exists, its entries are
    merged on top of the bundled rules (disable/overrides/add/thresholds).
    """
    with yaml_path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    if user_yaml_path is not None and user_yaml_path.exists():
        with user_yaml_path.open("r", encoding="utf-8") as f:
            user_raw = yaml.safe_load(f) or {}
        if isinstance(user_raw, dict):
            raw = _apply_user_overrides(raw, user_raw)

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
        severity = entry.get("severity", "ERROR")
        category = entry.get("category", "")
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
                        severity=severity,
                        category=category,
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


_REPLACEMENT_MAX_CHARS = 30


def extract_replacement(suggest: str) -> str | None:
    """Pick the first comma-separated chunk of ``suggest`` as an auto-replacement.

    ``banned_terms.yaml`` stores ``suggest`` as a free-form guidance string such
    as ``"限定的な変更、今回の範囲"``. The first chunk before a Japanese or
    ASCII comma is usually the primary replacement. Returns ``None`` when the
    chunk is empty or looks too descriptive to substitute safely.
    """
    if not suggest:
        return None
    first = re.split(r"[、,]", suggest, maxsplit=1)[0].strip()
    if not first:
        return None
    if len(first) > _REPLACEMENT_MAX_CHARS:
        return None
    return first


def _replace_outside_code_spans(line: str, terms: dict[str, str]) -> str:
    """Replace ``terms`` in ``line`` but not inside backtick spans or markdown link URLs."""
    pattern = re.compile(r"(`[^`]*`|\[[^\]]*\]\([^)]*\))")
    parts = pattern.split(line)
    out: list[str] = []
    for idx, part in enumerate(parts):
        if idx % 2 == 1:
            # Code span or markdown link — leave untouched.
            out.append(part)
            continue
        for term, replacement in terms.items():
            term_re = re.compile(
                r"(?<![A-Za-z0-9_])" + re.escape(term) + r"(?![A-Za-z0-9_-])",
                re.IGNORECASE,
            )
            part = term_re.sub(replacement, part)
        out.append(part)
    return "".join(out)


def apply_auto_fix(draft: str, violations: list[Violation]) -> str:
    """Return ``draft`` with each fixable banned-term violation replaced.

    Only ``banned_term`` violations whose ``suggest`` has an extractable
    replacement are applied. Text inside fenced code blocks, inline backtick
    spans, or markdown-link URLs is preserved verbatim. Unknown rule types are
    ignored — the server decides which violations to route through the fast
    path before calling this.
    """
    terms_to_replace: dict[str, str] = {}
    for v in violations:
        if v.rule != "banned_term" or not v.term:
            continue
        replacement = extract_replacement(v.suggest)
        if replacement and v.term not in terms_to_replace:
            terms_to_replace[v.term] = replacement
    if not terms_to_replace:
        return draft

    # Split by fenced code blocks; replacements happen only in non-code parts.
    parts = re.split(r"(```.*?```)", draft, flags=re.DOTALL)
    out: list[str] = []
    for idx, part in enumerate(parts):
        if idx % 2 == 1:
            out.append(part)
            continue
        lines_out = [
            _replace_outside_code_spans(line, terms_to_replace) for line in part.split("\n")
        ]
        out.append("\n".join(lines_out))
    return "".join(out)


def _wrap_bare_identifiers_in_line(line: str, pattern: re.Pattern[str]) -> str:
    """Wrap each regex-matched bare identifier in backticks, skipping code spans."""
    code_span_re = re.compile(r"(`[^`]*`|\[[^\]]*\]\([^)]*\))")
    parts = code_span_re.split(line)
    out: list[str] = []
    for idx, part in enumerate(parts):
        if idx % 2 == 1:
            out.append(part)  # already inside a code span or markdown link
            continue
        out.append(pattern.sub(lambda m: f"`{m.group(0)}`", part))
    return "".join(out)


def apply_backtick_fix(draft: str, cfg: RuleConfig) -> str:
    """Return ``draft`` with every bare code-identifier wrapped in backticks.

    The wrap is safe: markdown inline code has no effect on prose rendering
    beyond visual emphasis, and once wrapped the token is masked from further
    lint detection (bare_identifier, too_many_identifiers, and the identifier-
    aware branch of sentence_too_long all rely on the same masking).
    """
    pattern = re.compile(cfg.identifier_pattern)
    # Preserve fenced code blocks verbatim.
    parts = re.split(r"(```.*?```)", draft, flags=re.DOTALL)
    out: list[str] = []
    for idx, part in enumerate(parts):
        if idx % 2 == 1:
            out.append(part)
            continue
        lines_out = [_wrap_bare_identifiers_in_line(line, pattern) for line in part.split("\n")]
        out.append("\n".join(lines_out))
    return "".join(out)
