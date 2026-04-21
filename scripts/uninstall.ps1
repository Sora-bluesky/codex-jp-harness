# ja-output-harness uninstaller (Windows / PowerShell 7+)
#
# Removes the ja-output-harness footprint from ~/.codex/:
#   * [mcp_servers.jp_lint] block in config.toml
#   * codex_hooks = true toggle in config.toml (only if installed by us)
#   * Stop / SessionStart entries in hooks.json that point at
#     ja-output-harness hook scripts
# AGENTS.md edits remain manual — we print a removal notice — because the
# rule block may coexist with other user-authored rules.

$ErrorActionPreference = "Stop"

$codexDir    = Join-Path $env:USERPROFILE ".codex"
$configPath  = Join-Path $codexDir "config.toml"
$hooksJson   = Join-Path $codexDir "hooks.json"

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

# 2. Remove codex_hooks = true line.
$codexHooksPattern = '(?m)^\s*codex_hooks\s*=\s*true\s*\r?\n?'
$withoutFlag = [regex]::Replace($config, $codexHooksPattern, '')
if ($withoutFlag -ne $config) {
    Set-Content -Path $configPath -Value $withoutFlag -NoNewline
    Write-Host "[ja-output-harness] Removed codex_hooks = true from config.toml" -ForegroundColor Green
}

# 3. hooks.json cleanup — prune jp-harness entries only.
if (Test-Path $hooksJson) {
    try {
        $parsed = Get-Content $hooksJson -Raw | ConvertFrom-Json
    } catch {
        Write-Warning "[ja-output-harness] hooks.json cannot be parsed ($($_.Exception.Message)); skipping."
        $parsed = $null
    }

    if ($null -ne $parsed -and $parsed.PSObject.Properties.Name -contains 'hooks') {
        $hooksObj = $parsed.hooks
        $removed  = 0
        $markers  = @('ja-output-harness', 'codex-jp-harness')

        function Test-IsOurs($entry) {
            if ($null -eq $entry) { return $false }
            if ($entry.PSObject.Properties.Name -contains 'hooks' -and $entry.hooks) {
                foreach ($item in $entry.hooks) {
                    $cmd = ''
                    if ($item.PSObject.Properties.Name -contains 'command') {
                        $cmd = [string]$item.command
                    }
                    foreach ($m in $markers) {
                        if ($cmd -like "*${m}*") { return $true }
                    }
                }
            }
            if ($entry.PSObject.Properties.Name -contains 'command') {
                $cmd = [string]$entry.command
                foreach ($m in $markers) {
                    if ($cmd -like "*${m}*") { return $true }
                }
            }
            return $false
        }

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

        if ($removed -gt 0) {
            $backup = "$hooksJson.bak"
            Copy-Item $hooksJson $backup -Force
            $remainingEvents = @($hooksObj.PSObject.Properties.Name)
            if ($remainingEvents.Count -eq 0) {
                Remove-Item $hooksJson -Force
                Write-Host "[ja-output-harness] Removed empty hooks.json (backup at $backup)" -ForegroundColor Green
            } else {
                $parsed.hooks = $hooksObj
                ($parsed | ConvertTo-Json -Depth 10) + "`n" | Set-Content -Path $hooksJson -NoNewline
                Write-Host "[ja-output-harness] Pruned $removed hook entry/entries from hooks.json" -ForegroundColor Green
            }
        } else {
            Write-Host "[ja-output-harness] No ja-output-harness hook entries found in hooks.json." -ForegroundColor Yellow
        }
    }
} else {
    Write-Host "[ja-output-harness] hooks.json not present; nothing to clean." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "[ja-output-harness] Manual step (still required):" -ForegroundColor Yellow
Write-Host "[ja-output-harness]   Edit ~/.codex/AGENTS.md and remove the quality-gate rule block." -ForegroundColor Yellow
Write-Host "[ja-output-harness]   The uninstaller does not touch AGENTS.md because user-authored rules may be interleaved." -ForegroundColor Yellow
Write-Host "[ja-output-harness] Then restart Codex (CLI or App)." -ForegroundColor Yellow
