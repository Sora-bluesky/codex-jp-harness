# ja-output-harness: SessionStart hook
#
# Reads ~/.codex/state/jp-harness.jsonl, filters un-expired un-consumed entries,
# emits a reeducation prompt (hard cap 400 chars) only when source is "startup"
# or "clear". "resume" is suppressed to avoid breaking existing context.
#
# Contract:
#   input  : stdin JSON  { session_id?, source?: "startup"|"resume"|"clear" }
#   output : stdout reeducation prompt (or empty)
#   exit   : 0 always

$ErrorActionPreference = 'Continue'
$maxChars = 400

# Force UTF-8 on stdin / stdout / stderr. Without this, on Japanese Windows the
# default console codepage (cp932) re-decodes the UTF-8 JSON payload that Codex
# pipes in, so Japanese characters (and the structure itself) break.
try { [Console]::InputEncoding  = [System.Text.UTF8Encoding]::new($false) } catch {}
try { [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false) } catch {}
try { $OutputEncoding = [System.Text.UTF8Encoding]::new($false) } catch {}

try {
    $source = 'startup'
    $raw = [Console]::In.ReadToEnd()
    if (-not [string]::IsNullOrWhiteSpace($raw)) {
        try {
            $payload = $raw | ConvertFrom-Json -ErrorAction Stop
            if ($null -ne $payload.source) { $source = [string]$payload.source }
        } catch {}
    }
    if ($source -eq 'resume') { exit 0 }

    $codexHome = $env:CODEX_HOME
    if ([string]::IsNullOrWhiteSpace($codexHome)) {
        $codexHome = Join-Path $env:USERPROFILE '.codex'
    }
    $stateFile = Join-Path $codexHome 'state\jp-harness.jsonl'
    if (-not (Test-Path $stateFile)) { exit 0 }

    $now   = [DateTime]::UtcNow
    $lines = Get-Content -Path $stateFile -Encoding utf8 -ErrorAction SilentlyContinue
    if ($null -eq $lines) { exit 0 }
    $tail  = @($lines | Select-Object -Last 20)

    $active = @()
    $keep   = @()
    foreach ($line in $tail) {
        if ([string]::IsNullOrWhiteSpace($line)) { continue }
        try {
            $entry = $line | ConvertFrom-Json -ErrorAction Stop
            $exp   = [DateTime]::Parse($entry.expires).ToUniversalTime()
            if ($exp -le $now) { continue }
            if ($null -ne $entry.consumed -and $entry.consumed) {
                $keep += $line
                continue
            }
            $active += $entry
        } catch {
            continue
        }
    }

    if ($active.Count -eq 0) { exit 0 }

    $groups = $active | Group-Object -Property violation |
        Sort-Object -Property Count -Descending | Select-Object -First 3
    $parts  = @()
    foreach ($g in $groups) {
        $parts += ("{0} ({1}回)" -f $g.Name, $g.Count)
    }
    $detail = ($parts -join '、')

    $msg = "[ja-output-harness] 前回セッションで mcp__jp_lint__finalize の呼び忘れを検出しました。" `
         + "内訳: $detail。" `
         + "日本語応答を返す前に必ず finalize を呼んでください。" `
         + "除外は 4 パターンのみ（コード単独 / 20字以内相槌 / yes-no / 日本語なし）。迷ったら呼ぶ。"
    if ($msg.Length -gt $maxChars) { $msg = $msg.Substring(0, $maxChars) }

    Write-Output $msg

    foreach ($a in $active) {
        $a | Add-Member -NotePropertyName consumed -NotePropertyValue $true -Force
        $keep += ($a | ConvertTo-Json -Compress)
    }
    Set-Content -Path $stateFile -Value $keep -Encoding utf8
    exit 0
} catch {
    try {
        [Console]::Error.WriteLine("[ja-output-harness] session-start-reeducate error: $_")
    } catch {}
    exit 0
}
