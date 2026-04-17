# codex-jp-harness installer (Windows / PowerShell 7+)
#
# Registers the jp-lint MCP server in ~/.codex/config.toml and prompts the
# user to add the finalize rule to ~/.codex/AGENTS.md (Phase A only; Phase C
# hook registration is added by a later script).

param(
    [switch]$Force
)

$ErrorActionPreference = "Stop"

# Paths
$repoRoot   = Split-Path -Parent $PSScriptRoot
$serverPath = Join-Path $repoRoot "src\codex_jp_harness\server.py"
$venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"
$codexDir   = Join-Path $env:USERPROFILE ".codex"
$configPath = Join-Path $codexDir "config.toml"
$agentsPath = Join-Path $codexDir "AGENTS.md"

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

# AGENTS.md advisory
if (Test-Path $agentsPath) {
    $agents = Get-Content $agentsPath -Raw
    if ($agents -notmatch 'mcp__jp_lint__finalize') {
        Write-Host ""
        Write-Host "[codex-jp-harness] WARNING: AGENTS.md does not reference finalize rule." -ForegroundColor Yellow
        Write-Host "[codex-jp-harness] Append the following block to your AGENTS.md:" -ForegroundColor Yellow
        Write-Host ""
        Write-Host "   p. 日本語の技術進捗報告等を返す直前に ``mcp__jp_lint__finalize`` を必ず呼び、" -ForegroundColor Cyan
        Write-Host "      ``ok: true`` を得たドラフトのみ返す。retry 上限 3 回。起動失敗時は自己検品で継続。" -ForegroundColor Cyan
        Write-Host ""
    } else {
        Write-Host "[codex-jp-harness] AGENTS.md references finalize rule. OK." -ForegroundColor Green
    }
} else {
    Write-Host "[codex-jp-harness] AGENTS.md not found; skipping rule check." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "[codex-jp-harness] Installation complete." -ForegroundColor Green
Write-Host "[codex-jp-harness] Restart Codex CLI to activate the MCP server." -ForegroundColor Green
