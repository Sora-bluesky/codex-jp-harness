# codex-jp-harness installer (Windows / PowerShell 7+)
#
# Registers the jp-lint MCP server in ~/.codex/config.toml and prompts the
# user to add the finalize rule to ~/.codex/AGENTS.md (Phase A only; Phase C
# hook registration is added by a later script).

param(
    [switch]$Force,
    [switch]$AppendAgentsRule,
    [switch]$SkipSkill,
    [switch]$EnableHooks,
    [switch]$ForceHooks
)

$ErrorActionPreference = "Stop"

# Paths
$repoRoot   = Split-Path -Parent $PSScriptRoot
$serverPath = Join-Path $repoRoot "src\codex_jp_harness\server.py"
$venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"
$skillSrc   = Join-Path $repoRoot "skills\jp-harness-tune\SKILL.md"
$codexDir   = Join-Path $env:USERPROFILE ".codex"
$configPath = Join-Path $codexDir "config.toml"
$agentsPath = Join-Path $codexDir "AGENTS.md"
$skillDestDir  = Join-Path $codexDir "skills\jp-harness-tune"
$skillDestPath = Join-Path $skillDestDir "SKILL.md"
$hooksJsonPath = Join-Path $codexDir "hooks.json"
$hooksTemplate = Join-Path $repoRoot "config\hooks.example.json"
$stopHookPath  = Join-Path $repoRoot "hooks\stop-finalize-check.ps1"
$startHookPath = Join-Path $repoRoot "hooks\session-start-reeducate.ps1"

# Preflight
if (-not (Test-Path $serverPath)) {
    Write-Error "server.py not found at $serverPath"
    exit 1
}
if (-not (Test-Path $codexDir)) {
    Write-Error "Codex directory not found at $codexDir. Is Codex CLI installed?"
    exit 1
}
if (-not (Test-Path $configPath)) {
    Write-Error "Codex config.toml not found at $configPath"
    exit 1
}
if (-not (Test-Path $venvPython)) {
    Write-Error @"
.venv Python not found at $venvPython.
Run 'uv sync' in the repo root first:
    cd $repoRoot
    uv sync
"@
    exit 1
}
if (-not $SkipSkill -and -not (Test-Path $skillSrc)) {
    Write-Error "SKILL.md not found at $skillSrc. Re-clone the repo or pass -SkipSkill to bypass."
    exit 1
}

# Read config
$config = Get-Content $configPath -Raw

# Remove any existing entry (idempotent re-install)
if ($config -match '\[mcp_servers\.jp_lint\]') {
    if (-not $Force) {
        Write-Host "[codex-jp-harness] [mcp_servers.jp_lint] already present. Rewriting to match current repo location." -ForegroundColor Yellow
    }
    $pattern = '(?ms)\r?\n\[mcp_servers\.jp_lint\].*?(?=\r?\n\[|\z)'
    $config = [regex]::Replace($config, $pattern, '')
    $config = $config.TrimEnd() + "`n"
    Set-Content -Path $configPath -Value $config -NoNewline
}

# Register MCP server (using the repo's .venv Python so deps are available)
$escapedPython = $venvPython -replace '\\', '\\'
$entry = @"

[mcp_servers.jp_lint]
command = "$escapedPython"
args = ["-m", "codex_jp_harness.server"]
"@
Add-Content -Path $configPath -Value $entry -NoNewline
Write-Host "[codex-jp-harness] Registered [mcp_servers.jp_lint] with venv Python: $venvPython" -ForegroundColor Green

# AGENTS.md rule handling
$ruleBlockPath = Join-Path $repoRoot "config\agents_rule.md"
if (Test-Path $agentsPath) {
    $agents = Get-Content $agentsPath -Raw
    if ($agents -match 'mcp__jp_lint__finalize') {
        Write-Host "[codex-jp-harness] AGENTS.md already references finalize rule. OK." -ForegroundColor Green
    } elseif ($AppendAgentsRule) {
        if (-not (Test-Path $ruleBlockPath)) {
            Write-Error "agents_rule.md not found at $ruleBlockPath"
            exit 1
        }
        # Strip HTML comments from rule block before appending
        $ruleRaw = Get-Content $ruleBlockPath -Raw
        $rulePart = [regex]::Replace($ruleRaw, '(?s)<!--.*?-->', '').TrimStart()
        # Ensure AGENTS.md ends with a newline before appending
        if (-not $agents.EndsWith("`n")) {
            Add-Content -Path $agentsPath -Value "`n" -NoNewline
        }
        Add-Content -Path $agentsPath -Value $rulePart -NoNewline
        Write-Host "[codex-jp-harness] Appended finalize rule block to AGENTS.md" -ForegroundColor Green
    } else {
        Write-Host ""
        Write-Host "[codex-jp-harness] AGENTS.md does not yet reference the finalize rule." -ForegroundColor Yellow
        Write-Host "[codex-jp-harness] Re-run with -AppendAgentsRule to append automatically," -ForegroundColor Yellow
        Write-Host "[codex-jp-harness] or manually append the content of config\agents_rule.md." -ForegroundColor Yellow
    }
} else {
    Write-Host "[codex-jp-harness] AGENTS.md not found; skipping rule handling." -ForegroundColor Yellow
}

# Skill placement
if ($SkipSkill) {
    Write-Host "[codex-jp-harness] Skipping skill placement (-SkipSkill)." -ForegroundColor Yellow
} else {
    if (-not (Test-Path $skillDestDir)) {
        New-Item -ItemType Directory -Path $skillDestDir -Force | Out-Null
    }
    if (-not (Test-Path $skillDestPath)) {
        Copy-Item -Path $skillSrc -Destination $skillDestPath -Force
        Write-Host "[codex-jp-harness] Installed skill: $skillDestPath" -ForegroundColor Green
    } else {
        $srcHash  = (Get-FileHash -Path $skillSrc       -Algorithm SHA256).Hash
        $destHash = (Get-FileHash -Path $skillDestPath  -Algorithm SHA256).Hash
        if ($srcHash -eq $destHash) {
            Write-Host "[codex-jp-harness] Skill up to date: $skillDestPath" -ForegroundColor Green
        } else {
            Write-Warning "Existing SKILL.md at $skillDestPath differs from the bundled version. Skip overwrite to preserve your edits. Remove the file manually and re-run to reinstall."
        }
    }
}

# Hooks placement (opt-in, experimental, Codex 0.120.0+)
if ($EnableHooks) {
    Write-Host ""
    Write-Host "[codex-jp-harness] -EnableHooks: configuring Stop + SessionStart hooks (experimental)." -ForegroundColor Cyan

    # Codex version gate
    $codexVersionOk = $false
    try {
        $codexVersionRaw = & codex --version 2>$null
        if ($LASTEXITCODE -eq 0 -and $codexVersionRaw) {
            $versionStr = ($codexVersionRaw | Out-String).Trim()
            if ($versionStr -match '(\d+)\.(\d+)\.(\d+)') {
                $major = [int]$Matches[1]; $minor = [int]$Matches[2]
                if (($major -gt 0) -or ($major -eq 0 -and $minor -ge 120)) {
                    $codexVersionOk = $true
                }
                Write-Host "[codex-jp-harness] Detected Codex version: $versionStr" -ForegroundColor Green
            }
        }
    } catch {}

    if (-not $codexVersionOk) {
        Write-Warning "Codex CLI 0.120.0 or later is required for hooks. Skipping hooks setup."
    } elseif (-not (Test-Path $stopHookPath) -or -not (Test-Path $startHookPath) -or -not (Test-Path $hooksTemplate)) {
        Write-Warning "Hooks source files missing in repo. Skipping hooks setup."
    } else {
        # Ensure codex_hooks = true in config.toml (idempotent)
        $currentConfig = Get-Content $configPath -Raw
        if ($currentConfig -match '(?m)^\s*codex_hooks\s*=\s*true\b') {
            Write-Host "[codex-jp-harness] codex_hooks = true already set in config.toml." -ForegroundColor Green
        } else {
            if (-not $currentConfig.EndsWith("`n")) {
                Add-Content -Path $configPath -Value "`n" -NoNewline
            }
            Add-Content -Path $configPath -Value "codex_hooks = true`n" -NoNewline
            Write-Host "[codex-jp-harness] Set codex_hooks = true in config.toml." -ForegroundColor Green
        }

        # Build hooks.json by substituting placeholders
        $template = Get-Content $hooksTemplate -Raw

        $stopAbs  = (Resolve-Path $stopHookPath).Path
        $startAbs = (Resolve-Path $startHookPath).Path
        # JSON-escape backslashes and double quotes
        $stopCmdRaw  = "pwsh -NoProfile -File `"$stopAbs`""
        $startCmdRaw = "pwsh -NoProfile -File `"$startAbs`""
        $stopCmdJson  = $stopCmdRaw  -replace '\\', '\\' -replace '"', '\"'
        $startCmdJson = $startCmdRaw -replace '\\', '\\' -replace '"', '\"'

        $rendered = $template.Replace('{{STOP_COMMAND}}', $stopCmdJson).Replace('{{SESSION_START_COMMAND}}', $startCmdJson)

        if (Test-Path $hooksJsonPath) {
            $existing = Get-Content $hooksJsonPath -Raw
            if ($existing.Trim() -eq $rendered.Trim()) {
                Write-Host "[codex-jp-harness] hooks.json already up to date." -ForegroundColor Green
            } elseif ($ForceHooks) {
                Set-Content -Path $hooksJsonPath -Value $rendered -NoNewline -Encoding utf8
                Write-Host "[codex-jp-harness] Overwrote existing hooks.json (-ForceHooks)." -ForegroundColor Yellow
            } else {
                Write-Warning "Existing hooks.json at $hooksJsonPath differs from the bundled template."
                Write-Warning "Review the difference and re-run with -ForceHooks to overwrite, or merge manually."
                Write-Warning "Bundled template path: $hooksTemplate"
            }
        } else {
            Set-Content -Path $hooksJsonPath -Value $rendered -NoNewline -Encoding utf8
            Write-Host "[codex-jp-harness] Wrote $hooksJsonPath" -ForegroundColor Green
        }
    }
}

Write-Host ""
Write-Host "[codex-jp-harness] Installation complete." -ForegroundColor Green
Write-Host "[codex-jp-harness] Restart Codex CLI to activate the MCP server and the jp-harness-tune skill." -ForegroundColor Green
if ($EnableHooks) {
    Write-Host "[codex-jp-harness] Hooks (experimental) require Codex CLI 0.120.0+. See docs/HOOKS.md for details." -ForegroundColor Green
}
