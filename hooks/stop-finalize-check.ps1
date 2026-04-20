# codex-jp-harness: Stop hook
#
# Determines whether the just-completed turn produced a Japanese assistant
# reply without calling mcp__jp_lint__finalize, and records a missing-finalize
# entry to ~/.codex/state/jp-harness.jsonl for the next SessionStart hook.
#
# Codex 0.120.x Stop hook stdin fields:
#   session_id, turn_id, transcript_path (nullable), cwd, hook_event_name,
#   model, permission_mode, stop_hook_active, last_assistant_message (nullable)
#
# Detection:
#   1. If last_assistant_message contains no Japanese characters -> skip.
#   2. If transcript_path is unavailable -> skip (fail-open).
#   3. Scan transcript for "finalize" string; if found -> skip.
#   4. Otherwise record missing-finalize entry.
#
# Contract:
#   output : stdout empty
#   exit   : 0 always (never break the session)

$ErrorActionPreference = 'Continue'
$schemaVersion = '1'

# Force UTF-8 on stdin / stdout / stderr. Without this, on Japanese Windows the
# default console codepage (cp932) re-decodes the UTF-8 JSON payload that Codex
# pipes in, so Japanese characters (and the structure itself) break.
try { [Console]::InputEncoding  = [System.Text.UTF8Encoding]::new($false) } catch {}
try { [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false) } catch {}
try { $OutputEncoding = [System.Text.UTF8Encoding]::new($false) } catch {}

try {
    $raw = [Console]::In.ReadToEnd()
    if ([string]::IsNullOrWhiteSpace($raw)) { exit 0 }

    try {
        $payload = $raw | ConvertFrom-Json -ErrorAction Stop
    } catch {
        exit 0
    }

    $lastMsg = ''
    if ($null -ne $payload.last_assistant_message) {
        $lastMsg = [string]$payload.last_assistant_message
    }
    if ([string]::IsNullOrWhiteSpace($lastMsg)) { exit 0 }

    # Japanese character range: Hiragana U+3040-309F, Katakana U+30A0-30FF,
    # CJK Unified Ideographs U+4E00-9FFF.
    if ($lastMsg -notmatch '[\u3040-\u309f\u30a0-\u30ff\u4e00-\u9fff]') {
        exit 0
    }

    $transcriptPath = ''
    if ($null -ne $payload.transcript_path) {
        $transcriptPath = [string]$payload.transcript_path
    }
    if ([string]::IsNullOrWhiteSpace($transcriptPath) -or -not (Test-Path $transcriptPath)) {
        # Fail-open: without the transcript we cannot tell whether finalize was called.
        exit 0
    }

    try {
        $transcript = Get-Content -Path $transcriptPath -Raw -Encoding utf8 -ErrorAction Stop
    } catch {
        exit 0
    }
    if ($transcript -match 'finalize') { exit 0 }

    $codexHome = $env:CODEX_HOME
    if ([string]::IsNullOrWhiteSpace($codexHome)) {
        $codexHome = Join-Path $env:USERPROFILE '.codex'
    }
    $stateDir  = Join-Path $codexHome 'state'
    $stateFile = Join-Path $stateDir 'jp-harness.jsonl'
    if (-not (Test-Path $stateDir)) {
        New-Item -ItemType Directory -Path $stateDir -Force | Out-Null
    }

    $now     = [DateTime]::UtcNow
    $expires = $now.AddHours(24)
    $entry = [ordered]@{
        schema_version = $schemaVersion
        ts             = $now.ToString("yyyy-MM-ddTHH:mm:ssZ")
        session        = [string]$payload.session_id
        violation      = 'missing-finalize'
        expires        = $expires.ToString("yyyy-MM-ddTHH:mm:ssZ")
    }
    $line = $entry | ConvertTo-Json -Compress
    Add-Content -Path $stateFile -Value $line -Encoding utf8
    exit 0
} catch {
    try {
        [Console]::Error.WriteLine("[codex-jp-harness] stop-finalize-check error: $_")
    } catch {}
    exit 0
}
