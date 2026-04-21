# ja-output-harness: Stop hook
#
# Behaviour varies with the installed mode (read from
# ~/.codex/state/jp-harness-mode, default "strict"):
#
#   strict      - v0.3.x behaviour. Detects a Japanese reply that skipped
#                 `mcp__jp_lint__finalize` and logs a missing-finalize entry
#                 for the next SessionStart hook to re-educate.
#
#   lite        - No MCP server is registered in this mode; the MCP
#                 gate would cost ~200% output tokens. Instead, we run
#                 the local `ja_output_harness.rules_cli` over the
#                 assistant message and append violations to
#                 jp-harness-lite.jsonl. Zero output tokens because the
#                 check runs outside the model loop.
#
#   strict-lite - Same lite lint, but on ERROR-severity violations we
#                 return `{"decision":"block","reason":...}` so Codex
#                 auto-creates a continuation turn to self-correct.
#                 excess overhead ~= p * retry_cost, typically ~0.15x.
#
# Codex 0.120.x Stop hook stdin fields:
#   session_id, turn_id, transcript_path (nullable), cwd, hook_event_name,
#   model, permission_mode, stop_hook_active, last_assistant_message (nullable)
#
# Contract:
#   output : stdout = JSON hook response (or empty for strict mode)
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

    $codexHome = $env:CODEX_HOME
    if ([string]::IsNullOrWhiteSpace($codexHome)) {
        $codexHome = Join-Path $env:USERPROFILE '.codex'
    }
    $stateDir  = Join-Path $codexHome 'state'
    if (-not (Test-Path $stateDir)) {
        New-Item -ItemType Directory -Path $stateDir -Force | Out-Null
    }

    # Mode marker (written by install.ps1 --mode). Default "strict" preserves
    # v0.3.x behaviour when the marker is missing.
    $modeFile = Join-Path $stateDir 'jp-harness-mode'
    $mode = 'strict'
    if (Test-Path $modeFile) {
        $mode = (Get-Content -Path $modeFile -Raw -Encoding utf8).Trim()
        if ([string]::IsNullOrWhiteSpace($mode)) { $mode = 'strict' }
    }

    if ($mode -eq 'lite' -or $mode -eq 'strict-lite') {
        # Resolve the repo root and venv python from this script's location.
        # $PSCommandPath is the absolute path of the executing script
        # (install.ps1 registers the hook by absolute path so this is stable).
        $scriptPath = $PSCommandPath
        if ([string]::IsNullOrWhiteSpace($scriptPath)) {
            $scriptPath = $MyInvocation.MyCommand.Path
        }
        $hookDir  = Split-Path -Parent $scriptPath
        $repoRoot = Split-Path -Parent $hookDir
        $venvPy   = Join-Path $repoRoot '.venv\Scripts\python.exe'
        if (-not (Test-Path $venvPy)) {
            # No venv available — fail-open silently.
            exit 0
        }

        # Write the assistant message to a UTF-8 temp file. heredoc / pipe
        # stdin is avoided because CRLF conversion and codepage decoding on
        # Windows corrupts Japanese text (gpt-5.4 review).
        $tempFile = [System.IO.Path]::GetTempFileName()
        try {
            [System.IO.File]::WriteAllText($tempFile, $lastMsg, [System.Text.UTF8Encoding]::new($false))
            $raw = & $venvPy -m ja_output_harness.rules_cli --check $tempFile 2>$null
            if ([string]::IsNullOrWhiteSpace($raw)) { exit 0 }
            try {
                $result = $raw | ConvertFrom-Json -ErrorAction Stop
            } catch {
                exit 0
            }

            $ruleCountsHash = @{}
            if ($null -ne $result.rule_counts) {
                $result.rule_counts.PSObject.Properties | ForEach-Object {
                    $ruleCountsHash[$_.Name] = $_.Value
                }
            }

            $liteStateFile = Join-Path $stateDir 'jp-harness-lite.jsonl'
            $now     = [DateTime]::UtcNow
            $expires = $now.AddHours(24)
            $entry = [ordered]@{
                schema_version   = '1'
                ts               = $now.ToString("yyyy-MM-ddTHH:mm:ssZ")
                session          = [string]$payload.session_id
                ok               = [bool]$result.ok
                violation_count  = [int]$result.violation_count
                rule_counts      = $ruleCountsHash
                mode             = $mode
                expires          = $expires.ToString("yyyy-MM-ddTHH:mm:ssZ")
            }
            $line = $entry | ConvertTo-Json -Compress
            Add-Content -Path $liteStateFile -Value $line -Encoding utf8

            # Codex sets stop_hook_active = true when the current Stop
            # event is itself the result of a prior Stop hook continuation.
            # Emitting another block in that case can infinite-loop when the
            # model cannot clean the violation in one try. Log only; do not
            # block. (gpt-5.4 review BLOCKER #2)
            $stopHookActive = $false
            if ($null -ne $payload.stop_hook_active) {
                $stopHookActive = [bool]$payload.stop_hook_active
            }

            if ($mode -eq 'strict-lite' -and -not $result.ok -and -not $stopHookActive) {
                # Build a short reason (<300 chars) listing top rules.
                $parts = @()
                foreach ($rule in $ruleCountsHash.Keys) {
                    $parts += ("${rule}: " + $ruleCountsHash[$rule])
                }
                $reason = "ja-output-harness lite: " + ($parts -join ', ') +
                    ". 違反箇所を修正してから再送してください。"
                $block = [ordered]@{
                    decision = 'block'
                    reason   = $reason
                }
                ($block | ConvertTo-Json -Compress)
            }
        } finally {
            if (Test-Path $tempFile) { Remove-Item $tempFile -Force -ErrorAction SilentlyContinue }
        }
        exit 0
    }

    # Strict mode (v0.3.x behaviour).
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
    # Require the jp_lint-scoped tool name to avoid confusion with any
    # other MCP server that might also expose a tool literally called
    # "finalize" (gpt-5.4 follow-up review MINOR).
    if ($transcript -match 'mcp__jp_lint__finalize') { exit 0 }

    $stateFile = Join-Path $stateDir 'jp-harness.jsonl'

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
        [Console]::Error.WriteLine("[ja-output-harness] stop-finalize-check error: $_")
    } catch {}
    exit 0
}
