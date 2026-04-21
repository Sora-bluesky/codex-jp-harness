# ja-output-harness installer (Windows / PowerShell 7+)
#
# Installs the harness in one of three modes:
#   lite         — no MCP server. Stop hook runs local lint for post-hoc
#                  violation logging. Zero output-token overhead.
#                  (default for new installs)
#   strict-lite  — same local lint, but Stop hook emits
#                  {"decision":"block",...} on ERROR to trigger Codex
#                  self-correction. ~0.15x excess overhead.
#   strict       — v0.3.x behaviour: registers the MCP finalize gate so
#                  Codex calls it before every Japanese reply. ~2x+ excess
#                  overhead but tightest real-time compliance.
#
# If -Mode is omitted, the installer preserves the mode recorded in
# ~/.codex/state/jp-harness-mode; if no record exists, "lite" is chosen.
#
# The installer writes the mode marker to ~/.codex/state/jp-harness-mode
# so the Stop hook can read it at runtime.

param(
    [ValidateSet("lite", "strict-lite", "strict", "")]
    [string]$Mode = "",
    [switch]$Force,
    [switch]$AppendAgentsRule,
    [switch]$SkipSkill,
    [switch]$EnableHooks,
    [switch]$ForceHooks
)

$ErrorActionPreference = "Stop"

# Paths
$repoRoot   = Split-Path -Parent $PSScriptRoot
$serverPath = Join-Path $repoRoot "src\ja_output_harness\server.py"
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
$stateDir      = Join-Path $codexDir "state"
$modeMarker    = Join-Path $stateDir "jp-harness-mode"

# Mode resolution: explicit flag > marker file > "lite" (new install default).
if ([string]::IsNullOrWhiteSpace($Mode)) {
    if (Test-Path $modeMarker) {
        try {
            $Mode = (Get-Content -Path $modeMarker -Raw -Encoding utf8).Trim()
        } catch {
            $Mode = ""
        }
    }
    if ([string]::IsNullOrWhiteSpace($Mode)) {
        $Mode = "lite"
    }
}
if ($Mode -notin @("lite", "strict-lite", "strict")) {
    Write-Error "Invalid -Mode '$Mode'. Expected lite, strict-lite, or strict."
    exit 1
}
Write-Host "[ja-output-harness] Mode: $Mode" -ForegroundColor Cyan

# lite / strict-lite require the Stop hook to run local lint. Force the
# hook setup on so users don't silently get no enforcement.
if ($Mode -in @("lite", "strict-lite")) {
    if (-not $EnableHooks) {
        Write-Host "[ja-output-harness] Mode '$Mode' requires hooks. Enabling." -ForegroundColor Cyan
        $EnableHooks = $true
    }
}

# Preflight
if (-not (Test-Path $serverPath)) {
    Write-Error "server.py not found at $serverPath"
    exit 1
}
if (-not (Test-Path $codexDir)) {
    Write-Error "Codex directory not found at $codexDir. Is Codex CLI or Codex App installed?"
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

# Remove any existing entry (idempotent re-install). In lite / strict-lite
# modes we deliberately leave the [mcp_servers.jp_lint] stanza absent so the
# MCP server is NOT spawned per turn — that is the source of the +200%
# output-token overhead we are trying to eliminate.
if ($config -match '\[mcp_servers\.jp_lint\]') {
    if (-not $Force) {
        Write-Host "[ja-output-harness] [mcp_servers.jp_lint] already present. Rewriting." -ForegroundColor Yellow
    }
    $pattern = '(?ms)\r?\n\[mcp_servers\.jp_lint\].*?(?=\r?\n\[|\z)'
    $config = [regex]::Replace($config, $pattern, '')
    $config = $config.TrimEnd() + "`n"
    Set-Content -Path $configPath -Value $config -NoNewline
}

if ($Mode -eq "strict") {
    # Register MCP server (using the repo's .venv Python so deps are available)
    $escapedPython = $venvPython -replace '\\', '\\'
    $entry = @"

[mcp_servers.jp_lint]
command = "$escapedPython"
args = ["-m", "ja_output_harness.server"]
"@
    Add-Content -Path $configPath -Value $entry -NoNewline
    Write-Host "[ja-output-harness] Registered [mcp_servers.jp_lint] (strict mode) with venv Python: $venvPython" -ForegroundColor Green
} else {
    Write-Host "[ja-output-harness] Skipped [mcp_servers.jp_lint] registration (mode=$Mode — local lint only)." -ForegroundColor Green
}

# Write the mode marker so the Stop hook can branch on it at runtime.
if (-not (Test-Path $stateDir)) {
    New-Item -ItemType Directory -Path $stateDir -Force | Out-Null
}
Set-Content -Path $modeMarker -Value $Mode -NoNewline -Encoding utf8
Write-Host "[ja-output-harness] Wrote mode marker: $modeMarker = $Mode" -ForegroundColor Green

# AGENTS.md rule handling — pick the rule block matching the install mode.
# strict uses the full rule that tells Codex to call mcp__jp_lint__finalize;
# lite / strict-lite use a shorter rule that describes the top-5 constraints
# because the MCP server is absent.
if ($Mode -eq "strict") {
    $ruleBlockPath = Join-Path $repoRoot "config\agents_rule.md"
} else {
    $ruleBlockPath = Join-Path $repoRoot "config\agents_rule_lite.md"
}
$ruleMarker = if ($Mode -eq "strict") { 'mcp__jp_lint__finalize' } else { 'ja-output-harness lite' }
if (Test-Path $agentsPath) {
    $agents = Get-Content $agentsPath -Raw
    if ($agents -match [regex]::Escape($ruleMarker)) {
        Write-Host "[ja-output-harness] AGENTS.md already contains the $Mode-mode rule. OK." -ForegroundColor Green
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
        Write-Host "[ja-output-harness] Appended finalize rule block to AGENTS.md" -ForegroundColor Green
    } else {
        Write-Host ""
        Write-Host "[ja-output-harness] AGENTS.md does not yet reference the finalize rule." -ForegroundColor Yellow
        Write-Host "[ja-output-harness] Re-run with -AppendAgentsRule to append automatically," -ForegroundColor Yellow
        Write-Host "[ja-output-harness] or manually append the content of config\agents_rule.md." -ForegroundColor Yellow
    }
} else {
    Write-Host "[ja-output-harness] AGENTS.md not found; skipping rule handling." -ForegroundColor Yellow
}

# Skill placement
if ($SkipSkill) {
    Write-Host "[ja-output-harness] Skipping skill placement (-SkipSkill)." -ForegroundColor Yellow
} else {
    if (-not (Test-Path $skillDestDir)) {
        New-Item -ItemType Directory -Path $skillDestDir -Force | Out-Null
    }
    if (-not (Test-Path $skillDestPath)) {
        Copy-Item -Path $skillSrc -Destination $skillDestPath -Force
        Write-Host "[ja-output-harness] Installed skill: $skillDestPath" -ForegroundColor Green
    } else {
        $srcHash  = (Get-FileHash -Path $skillSrc       -Algorithm SHA256).Hash
        $destHash = (Get-FileHash -Path $skillDestPath  -Algorithm SHA256).Hash
        if ($srcHash -eq $destHash) {
            Write-Host "[ja-output-harness] Skill up to date: $skillDestPath" -ForegroundColor Green
        } else {
            Write-Warning "Existing SKILL.md at $skillDestPath differs from the bundled version. Skip overwrite to preserve your edits. Remove the file manually and re-run to reinstall."
        }
    }
}

# Hooks placement (opt-in, experimental, Codex 0.120.0+)
if ($EnableHooks) {
    Write-Host ""
    Write-Host "[ja-output-harness] -EnableHooks: configuring Stop + SessionStart hooks (experimental)." -ForegroundColor Cyan

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
                Write-Host "[ja-output-harness] Detected Codex version: $versionStr" -ForegroundColor Green
            }
        }
    } catch {}

    if (-not $codexVersionOk) {
        Write-Warning "Codex 0.120.0 or later (CLI or App) is required for hooks. Skipping hooks setup."
    } elseif (-not (Test-Path $stopHookPath) -or -not (Test-Path $startHookPath) -or -not (Test-Path $hooksTemplate)) {
        Write-Warning "Hooks source files missing in repo. Skipping hooks setup."
    } else {
        # Ensure codex_hooks = true in config.toml (idempotent)
        $currentConfig = Get-Content $configPath -Raw
        if ($currentConfig -match '(?m)^\s*codex_hooks\s*=\s*true\b') {
            Write-Host "[ja-output-harness] codex_hooks = true already set in config.toml." -ForegroundColor Green
        } else {
            if (-not $currentConfig.EndsWith("`n")) {
                Add-Content -Path $configPath -Value "`n" -NoNewline
            }
            Add-Content -Path $configPath -Value "codex_hooks = true`n" -NoNewline
            Write-Host "[ja-output-harness] Set codex_hooks = true in config.toml." -ForegroundColor Green
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
                Write-Host "[ja-output-harness] hooks.json already up to date." -ForegroundColor Green
            } elseif ($ForceHooks) {
                Set-Content -Path $hooksJsonPath -Value $rendered -NoNewline -Encoding utf8
                Write-Host "[ja-output-harness] Overwrote existing hooks.json (-ForceHooks)." -ForegroundColor Yellow
            } else {
                Write-Warning "Existing hooks.json at $hooksJsonPath differs from the bundled template."
                Write-Warning "Review the difference and re-run with -ForceHooks to overwrite, or merge manually."
                Write-Warning "Bundled template path: $hooksTemplate"
            }
        } else {
            Set-Content -Path $hooksJsonPath -Value $rendered -NoNewline -Encoding utf8
            Write-Host "[ja-output-harness] Wrote $hooksJsonPath" -ForegroundColor Green
        }
    }
}

Write-Host ""
Write-Host "[ja-output-harness] Installation complete." -ForegroundColor Green
Write-Host "[ja-output-harness] Restart Codex (CLI or App) to activate the MCP server and the jp-harness-tune skill." -ForegroundColor Green
if ($EnableHooks) {
    Write-Host "[ja-output-harness] Hooks (experimental) require Codex 0.120.0+ (CLI or App). See docs/HOOKS.md for details." -ForegroundColor Green
}
