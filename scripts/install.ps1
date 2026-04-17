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

# Check Python / uv
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    Write-Error "python not found in PATH. Install Python 3.11+ first."
    exit 1
}

# Read config
$config = Get-Content $configPath -Raw

# Register MCP server
if ($config -match '\[mcp_servers\.jp_lint\]' -and -not $Force) {
    Write-Host "[codex-jp-harness] [mcp_servers.jp_lint] already present. Use -Force to rewrite." -ForegroundColor Yellow
} else {
    $escapedPath = $serverPath -replace '\\', '\\'
    $entry = @"

[mcp_servers.jp_lint]
command = "python"
args = ["$escapedPath"]
"@
    Add-Content -Path $configPath -Value $entry -NoNewline
    Write-Host "[codex-jp-harness] Added [mcp_servers.jp_lint] to config.toml" -ForegroundColor Green
}

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
