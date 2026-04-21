# ja-output-harness uninstaller (Windows / PowerShell 7+)
#
# Removes the ja-output-harness footprint from ~/.codex/:
#   * [mcp_servers.jp_lint] block in config.toml
#   * Stop / SessionStart entries in hooks.json whose command invokes this
#     repo's hook scripts (absolute path match, plus repo marker fallback)
#   * codex_hooks = true toggle — only when no hooks remain after pruning,
#     so coexisting non-jp-harness hooks are never silently disabled
# AGENTS.md edits remain manual because the rule block often interleaves
# with user-authored rules.

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $PSCommandPath
$repoRoot  = Split-Path -Parent $scriptDir

$codexDir    = Join-Path $env:USERPROFILE ".codex"
$configPath  = Join-Path $codexDir "config.toml"
$hooksJson   = Join-Path $codexDir "hooks.json"
$stopHookAbs  = Join-Path $repoRoot "hooks\stop-finalize-check.ps1"
$startHookAbs = Join-Path $repoRoot "hooks\session-start-reeducate.ps1"

if (-not (Test-Path $configPath)) {
    Write-Error "Codex config.toml not found at $configPath"
    exit 1
}

# 1. Remove [mcp_servers.jp_lint] block.
$config = Get-Content $configPath -Raw
$pattern = '(?ms)\r?\n\[mcp_servers\.jp_lint\].*?(?=\r?\n\[|\z)'
$updated = [regex]::Replace($config, $pattern, '')

if ($updated -eq $config) {
    Write-Host "[ja-output-harness] [mcp_servers.jp_lint] not found; skipping." -ForegroundColor Yellow
} else {
    $backup = "$configPath.bak"
    Copy-Item $configPath $backup -Force
    Set-Content -Path $configPath -Value $updated -NoNewline
    Write-Host "[ja-output-harness] Removed [mcp_servers.jp_lint] from config.toml" -ForegroundColor Green
    Write-Host "[ja-output-harness] Backup saved to $backup" -ForegroundColor Green
    $config = $updated
}

# 2. hooks.json cleanup — prune jp-harness entries, track whether anything
#    remains so step 3 knows if codex_hooks can be removed safely.
$hooksEmpty = $true
$markers    = @('ja-output-harness', 'codex-jp-harness')
$ownedPaths = @($stopHookAbs, $startHookAbs) | Where-Object { $_ }

function Test-IsOurs($entry) {
    if ($null -eq $entry) { return $false }
    $cmds = @()
    if ($entry.PSObject.Properties.Name -contains 'hooks' -and $entry.hooks) {
        foreach ($item in $entry.hooks) {
            if ($item.PSObject.Properties.Name -contains 'command') {
                $cmds += [string]$item.command
            }
        }
    }
    if ($entry.PSObject.Properties.Name -contains 'command') {
        $cmds += [string]$entry.command
    }
    foreach ($cmd in $cmds) {
        if ([string]::IsNullOrEmpty($cmd)) { continue }
        foreach ($owned in $ownedPaths) {
            if ($owned -and $cmd.Contains($owned)) { return $true }
        }
        foreach ($m in $markers) {
            if ($cmd -like "*${m}*") { return $true }
        }
    }
    return $false
}

if (Test-Path $hooksJson) {
    try {
        $parsed = Get-Content $hooksJson -Raw | ConvertFrom-Json
    } catch {
        Write-Warning "[ja-output-harness] hooks.json cannot be parsed ($($_.Exception.Message)); skipping."
        $parsed = $null
        $hooksEmpty = $false
    }

    if ($null -ne $parsed -and $parsed.PSObject.Properties.Name -contains 'hooks') {
        $hooksObj = $parsed.hooks
        $removed  = 0

        $events = @($hooksObj.PSObject.Properties.Name)
        foreach ($event in $events) {
            $entries = @($hooksObj.$event)
            $kept = @($entries | Where-Object { -not (Test-IsOurs $_) })
            $removed += ($entries.Count - $kept.Count)
            if ($kept.Count -gt 0) {
                $hooksObj.$event = $kept
            } else {
                $hooksObj.PSObject.Properties.Remove($event)
            }
        }

        $remainingEvents = @($hooksObj.PSObject.Properties.Name)
        if ($removed -gt 0) {
            $backup = "$hooksJson.bak"
            Copy-Item $hooksJson $backup -Force
            if ($remainingEvents.Count -eq 0) {
                Remove-Item $hooksJson -Force
                Write-Host "[ja-output-harness] Removed empty hooks.json (backup at $backup)" -ForegroundColor Green
                $hooksEmpty = $true
            } else {
                $parsed.hooks = $hooksObj
                ($parsed | ConvertTo-Json -Depth 10) + "`n" | Set-Content -Path $hooksJson -NoNewline
                Write-Host "[ja-output-harness] Pruned $removed hook entry/entries from hooks.json" -ForegroundColor Green
                $hooksEmpty = $false
            }
        } else {
            if ($remainingEvents.Count -eq 0) {
                $hooksEmpty = $true
            } else {
                $hooksEmpty = $false
            }
            Write-Host "[ja-output-harness] No ja-output-harness hook entries found in hooks.json." -ForegroundColor Yellow
        }
    }
} else {
    Write-Host "[ja-output-harness] hooks.json not present; nothing to clean." -ForegroundColor Yellow
}

# 3. Remove codex_hooks = true only when no hooks remain.
$codexHooksPattern = '(?m)^\s*codex_hooks\s*=\s*true\s*\r?\n?'
if ([regex]::IsMatch($config, $codexHooksPattern)) {
    if ($hooksEmpty) {
        $withoutFlag = [regex]::Replace($config, $codexHooksPattern, '')
        Set-Content -Path $configPath -Value $withoutFlag -NoNewline
        Write-Host "[ja-output-harness] Removed codex_hooks = true from config.toml (no remaining hooks)." -ForegroundColor Green
    } else {
        Write-Host "[ja-output-harness] Left codex_hooks = true in place — other hooks are still registered in hooks.json." -ForegroundColor Yellow
    }
}

# 4. Remove the mode marker so a future install default re-enters the
#    "new user" path and writes the current default rather than restoring
#    the previous mode.
$modeMarker = Join-Path $codexDir "state\jp-harness-mode"
if (Test-Path $modeMarker) {
    Remove-Item $modeMarker -Force
    Write-Host "[ja-output-harness] Removed mode marker: $modeMarker" -ForegroundColor Green
}

# 5. Remove the SessionStart consumption cursor so a future install starts
#    from a clean slate rather than resuming a stale offset against a
#    different state layout.
$cursorFile = Join-Path $codexDir "state\jp-harness-cursor.json"
if (Test-Path $cursorFile) {
    Remove-Item $cursorFile -Force
    Write-Host "[ja-output-harness] Removed cursor file: $cursorFile" -ForegroundColor Green
}

Write-Host ""
Write-Host "[ja-output-harness] Manual step (still required):" -ForegroundColor Yellow
Write-Host "[ja-output-harness]   Edit ~/.codex/AGENTS.md and remove the quality-gate rule block." -ForegroundColor Yellow
Write-Host "[ja-output-harness]   The uninstaller does not touch AGENTS.md because user-authored rules may be interleaved." -ForegroundColor Yellow
Write-Host "[ja-output-harness] Then restart Codex (CLI or App)." -ForegroundColor Yellow
