# ja-output-harness: SessionStart hook
#
# Reads new entries from both harness jsonl files and emits a short
# reeducation prompt (hard cap 400 chars).
#
#   ~/.codex/state/jp-harness.jsonl       strict-mode missing-finalize logs
#   ~/.codex/state/jp-harness-lite.jsonl  lite / strict-lite ok=false logs
#
# Consumption is tracked by byte offset in
# ~/.codex/state/jp-harness-cursor.json so concurrent Stop-hook appends can
# never be overwritten and unprocessed rows outside a tail window can never
# be silently dropped (gpt-5.4 v0.4.0 review MAJOR #2/#3). The cursor file
# is written via temp + atomic move.
#
# Triggers on "startup" and "clear"; "resume" is suppressed to avoid
# injecting prompts mid-conversation.
#
# Contract:
#   input  : stdin JSON  { session_id?, source?: "startup"|"resume"|"clear" }
#   output : stdout reeducation prompt (or empty)
#   exit   : 0 always

$ErrorActionPreference = 'Continue'
$maxChars = 400

# Force UTF-8 on stdin / stdout / stderr so Japanese text survives cp932
# re-decoding on Windows consoles.
try { [Console]::InputEncoding  = [System.Text.UTF8Encoding]::new($false) } catch {}
try { [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false) } catch {}
try { $OutputEncoding = [System.Text.UTF8Encoding]::new($false) } catch {}

function Read-NewEntries {
    param([string]$Path, [long]$Offset)
    $result = @{ Entries = @(); NewOffset = $Offset }
    if (-not (Test-Path $Path)) { return $result }
    $size = (Get-Item $Path).Length
    if ($size -lt $Offset) {
        # File shrunk (unexpected rotation). Start fresh.
        $Offset = 0
    }
    if ($size -eq $Offset) {
        $result.NewOffset = $size
        return $result
    }
    $fs = $null
    $reader = $null
    try {
        $fs = [System.IO.File]::Open($Path, 'Open', 'Read', 'ReadWrite')
        [void]$fs.Seek($Offset, 'Begin')
        $reader = New-Object System.IO.StreamReader($fs, [System.Text.UTF8Encoding]::new($false))
        $content = $reader.ReadToEnd()
    } catch {
        return $result
    } finally {
        if ($null -ne $reader) { $reader.Dispose() }
        if ($null -ne $fs) { $fs.Dispose() }
    }
    $entries = @()
    foreach ($line in $content -split "`n") {
        if ([string]::IsNullOrWhiteSpace($line)) { continue }
        try {
            $entries += ($line | ConvertFrom-Json -ErrorAction Stop)
        } catch { continue }
    }
    $result.Entries = $entries
    $result.NewOffset = $size
    return $result
}

function Save-Cursor {
    param([string]$Path, [hashtable]$Data)
    $tmp = "$Path.tmp"
    try {
        ($Data | ConvertTo-Json -Compress) | Set-Content -Path $tmp -Encoding utf8 -NoNewline
        # .NET File.Move with overwrite=true is atomic on NTFS (PowerShell 7+).
        [System.IO.File]::Move($tmp, $Path, $true)
    } catch {
        if (Test-Path $tmp) { Remove-Item $tmp -Force -ErrorAction SilentlyContinue }
    }
}

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
    $stateDir = Join-Path $codexHome 'state'
    if (-not (Test-Path $stateDir)) { exit 0 }

    $strictFile = Join-Path $stateDir 'jp-harness.jsonl'
    $liteFile   = Join-Path $stateDir 'jp-harness-lite.jsonl'
    $cursorFile = Join-Path $stateDir 'jp-harness-cursor.json'

    $cursor = @{ strict_byte_offset = 0L; lite_byte_offset = 0L }
    if (Test-Path $cursorFile) {
        try {
            $existing = Get-Content -Path $cursorFile -Raw -Encoding utf8 | ConvertFrom-Json -ErrorAction Stop
            if ($null -ne $existing.strict_byte_offset) {
                $cursor.strict_byte_offset = [long]$existing.strict_byte_offset
            }
            if ($null -ne $existing.lite_byte_offset) {
                $cursor.lite_byte_offset = [long]$existing.lite_byte_offset
            }
        } catch {}
    } else {
        # First run: skip any pre-install history so a stale backlog doesn't
        # get blasted into the first session as a single 400-char prompt.
        if (Test-Path $strictFile) { $cursor.strict_byte_offset = (Get-Item $strictFile).Length }
        if (Test-Path $liteFile)   { $cursor.lite_byte_offset   = (Get-Item $liteFile).Length }
        Save-Cursor -Path $cursorFile -Data $cursor
        exit 0
    }

    $strictResult = Read-NewEntries -Path $strictFile -Offset $cursor.strict_byte_offset
    $liteResult   = Read-NewEntries -Path $liteFile   -Offset $cursor.lite_byte_offset

    $now = [DateTime]::UtcNow

    # Filter unexpired strict missing-finalize entries.
    $strictViolations = @()
    foreach ($e in $strictResult.Entries) {
        if ([string]::IsNullOrWhiteSpace([string]$e.violation)) { continue }
        try {
            $exp = [DateTime]::Parse($e.expires).ToUniversalTime()
        } catch { continue }
        if ($exp -le $now) { continue }
        $strictViolations += $e
    }

    # Filter unexpired lite ok=false entries.
    $liteViolations = @()
    foreach ($e in $liteResult.Entries) {
        if ($null -eq $e.ok) { continue }
        if ([bool]$e.ok) { continue }
        try {
            $exp = [DateTime]::Parse($e.expires).ToUniversalTime()
            if ($exp -le $now) { continue }
        } catch {}
        $liteViolations += $e
    }

    # Always persist the new cursor so we don't re-scan the same tail next
    # startup, even if this run produces no prompt.
    $cursor.strict_byte_offset = $strictResult.NewOffset
    $cursor.lite_byte_offset   = $liteResult.NewOffset
    Save-Cursor -Path $cursorFile -Data $cursor

    $parts = @()
    if ($strictViolations.Count -gt 0) {
        $top = $strictViolations | Group-Object -Property violation |
            Sort-Object -Property Count -Descending | Select-Object -First 3
        $detail = (@($top | ForEach-Object { "{0} ({1}回)" -f $_.Name, $_.Count }) -join '、')
        $parts += "前回セッションで mcp__jp_lint__finalize の呼び忘れ $($strictViolations.Count) 件（${detail}）。日本語応答の前に必ず finalize を呼ぶこと。除外は 4 パターンのみ（コード単独 / 20字以内相槌 / yes-no / 日本語なし）。"
    }
    if ($liteViolations.Count -gt 0) {
        $ruleAgg = @{}
        foreach ($v in $liteViolations) {
            if ($null -eq $v.rule_counts) { continue }
            foreach ($prop in $v.rule_counts.PSObject.Properties) {
                if (-not $ruleAgg.ContainsKey($prop.Name)) { $ruleAgg[$prop.Name] = 0 }
                try { $ruleAgg[$prop.Name] += [int]$prop.Value } catch {}
            }
        }
        $topRules = $ruleAgg.GetEnumerator() | Sort-Object -Property Value -Descending | Select-Object -First 3
        if ($topRules) {
            $ruleDetail = (@($topRules | ForEach-Object { "$($_.Key) ($($_.Value)回)" }) -join '、')
            $parts += "前回セッションで日本語品質違反 $($liteViolations.Count) 件（${ruleDetail}）。違反ルールを避けて応答すること。"
        } else {
            $parts += "前回セッションで日本語品質違反 $($liteViolations.Count) 件。"
        }
    }

    if ($parts.Count -eq 0) { exit 0 }

    $msg = "[ja-output-harness] " + ($parts -join ' ')
    if ($msg.Length -gt $maxChars) { $msg = $msg.Substring(0, $maxChars) }
    Write-Output $msg
    exit 0
} catch {
    try {
        [Console]::Error.WriteLine("[ja-output-harness] session-start-reeducate error: $_")
    } catch {}
    exit 0
}
