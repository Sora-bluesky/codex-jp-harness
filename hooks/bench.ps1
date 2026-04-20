# codex-jp-harness: hooks benchmark (Windows / PowerShell 7+)
#
# Runs each hook 10 times with synthetic payload and reports mean / max latency.
# Targets:
#   Stop hook        : < 50 ms (mean)
#   SessionStart hook: < 100 ms (mean)
#
# Usage:
#   pwsh hooks\bench.ps1

$ErrorActionPreference = 'Stop'

$hookDir = Split-Path -Parent $PSCommandPath
$stopHook = Join-Path $hookDir 'stop-finalize-check.ps1'
$startHook = Join-Path $hookDir 'session-start-reeducate.ps1'

$stopPayload = @{
    session_id = 'bench-session'
    turn_id = 'bench-turn'
    transcript_path = $null
    last_assistant_message = 'これは日本語の応答です。finalize を呼ばずに終わったケースの検査。'
    stop_hook_active = $false
    hook_event_name = 'Stop'
} | ConvertTo-Json -Compress

$startPayload = @{
    session_id = 'bench-session'
    source = 'startup'
    hook_event_name = 'SessionStart'
} | ConvertTo-Json -Compress

function Measure-Hook {
    param(
        [string]$Name,
        [string]$ScriptPath,
        [string]$Payload,
        [int]$Target
    )
    $durations = @()
    for ($i = 0; $i -lt 10; $i++) {
        $sw = [System.Diagnostics.Stopwatch]::StartNew()
        $Payload | pwsh -NoProfile -File $ScriptPath | Out-Null
        $sw.Stop()
        $durations += $sw.Elapsed.TotalMilliseconds
    }
    $mean = ($durations | Measure-Object -Average).Average
    $max  = ($durations | Measure-Object -Maximum).Maximum
    $status = if ($mean -le $Target) { 'PASS' } else { 'WARN' }
    Write-Host ("[{0}] {1}: mean={2:F1} ms, max={3:F1} ms (target <{4} ms)" -f $status, $Name, $mean, $max, $Target)
}

Write-Host '[codex-jp-harness] hooks benchmark (10 runs each)'
Measure-Hook -Name 'Stop'         -ScriptPath $stopHook  -Payload $stopPayload  -Target 50
Measure-Hook -Name 'SessionStart' -ScriptPath $startHook -Payload $startPayload -Target 100
