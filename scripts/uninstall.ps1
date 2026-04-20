# codex-jp-harness uninstaller (Windows / PowerShell 7+)
#
# Removes the jp-lint MCP server registration from ~/.codex/config.toml.
# AGENTS.md edits are NOT automatic — we print a manual removal notice.

$ErrorActionPreference = "Stop"

$codexDir   = Join-Path $env:USERPROFILE ".codex"
$configPath = Join-Path $codexDir "config.toml"

if (-not (Test-Path $configPath)) {
    Write-Error "Codex config.toml not found at $configPath"
    exit 1
}

$config = Get-Content $configPath -Raw

# Remove [mcp_servers.jp_lint] block (section until next blank [section] header or EOF)
$pattern = '(?ms)\r?\n\[mcp_servers\.jp_lint\].*?(?=\r?\n\[|\z)'
$updated = [regex]::Replace($config, $pattern, '')

if ($updated -eq $config) {
    Write-Host "[codex-jp-harness] [mcp_servers.jp_lint] not found; nothing to remove." -ForegroundColor Yellow
} else {
    # Backup
    $backup = "$configPath.bak"
    Copy-Item $configPath $backup -Force
    Set-Content -Path $configPath -Value $updated -NoNewline
    Write-Host "[codex-jp-harness] Removed [mcp_servers.jp_lint] from config.toml" -ForegroundColor Green
    Write-Host "[codex-jp-harness] Backup saved to $backup" -ForegroundColor Green
}

Write-Host ""
Write-Host "[codex-jp-harness] Manual step required:" -ForegroundColor Yellow
Write-Host "[codex-jp-harness]   1. Edit ~/.codex/AGENTS.md and remove the quality-gate rule block." -ForegroundColor Yellow
Write-Host "[codex-jp-harness]   2. Restart Codex (CLI or App)." -ForegroundColor Yellow
