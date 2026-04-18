# codex-jp-harness installer (Windows / PowerShell 7+)
#
# Registers the jp-lint MCP server in ~/.codex/config.toml and prompts the
# user to add the finalize rule to ~/.codex/AGENTS.md (Phase A only; Phase C
# hook registration is added by a later script).

param(
    [switch]$Force,
    [switch]$AppendAgentsRule,
    [switch]$SkipSkill
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

Write-Host ""
Write-Host "[codex-jp-harness] Installation complete." -ForegroundColor Green
Write-Host "[codex-jp-harness] Restart Codex CLI to activate the MCP server and the jp-harness-tune skill." -ForegroundColor Green
