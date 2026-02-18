# Orion Agent -- Pre-Push Validation Script (Windows PowerShell)
# Run this before pushing to ensure CI will pass.
#
# Usage: .\scripts\pre-push-check.ps1

$ErrorActionPreference = "Stop"

Write-Host "=== Orion Pre-Push Check ===" -ForegroundColor Cyan
Write-Host ""

# 1. Ruff Lint
Write-Host "[1/5] Ruff Lint..." -ForegroundColor Yellow
ruff check src/orion/ tests/
if ($LASTEXITCODE -ne 0) { Write-Host "FAIL: Ruff lint errors" -ForegroundColor Red; exit 1 }
Write-Host "  PASS" -ForegroundColor Green

# 2. Ruff Format
Write-Host "[2/5] Ruff Format..." -ForegroundColor Yellow
ruff format --check src/orion/ tests/
if ($LASTEXITCODE -ne 0) { Write-Host "FAIL: Ruff format errors" -ForegroundColor Red; exit 1 }
Write-Host "  PASS" -ForegroundColor Green

# 3. Secret Scan
Write-Host "[3/5] Secret Scan..." -ForegroundColor Yellow
$patterns = @(
    @{ Name = "OpenAI API key"; Pattern = "sk-[a-zA-Z0-9]{20,}"; Paths = @("src/", "data/", "docker/", "orion-web/src/") },
    @{ Name = "AWS access key"; Pattern = "AKIA[A-Z0-9]{16}"; Paths = @("src/", "data/", "docker/") },
    @{ Name = "Google API key"; Pattern = "AIza[a-zA-Z0-9]{30,}"; Paths = @("src/", "data/", "docker/", "orion-web/src/") },
    @{ Name = "GitHub token"; Pattern = "ghp_[a-zA-Z0-9]{20,}"; Paths = @("src/", "data/", "docker/") }
)
$secretFound = $false
foreach ($p in $patterns) {
    foreach ($searchPath in $p.Paths) {
        $fullPath = Join-Path $PSScriptRoot ".." $searchPath
        if (Test-Path $fullPath) {
            $matches = Get-ChildItem -Path $fullPath -Recurse -Include *.py,*.ts,*.tsx,*.json,*.yaml,*.yml,*.sh -ErrorAction SilentlyContinue |
                Select-String -Pattern $p.Pattern -ErrorAction SilentlyContinue |
                Where-Object { $_.Path -notmatch "test_" -and $_.Path -notmatch "test\\\\ara" }
            if ($matches) {
                Write-Host "  WARNING: Potential $($p.Name) found:" -ForegroundColor Red
                $matches | ForEach-Object { Write-Host "    $_" }
                $secretFound = $true
            }
        }
    }
}
if ($secretFound) { Write-Host "FAIL: Secrets detected" -ForegroundColor Red; exit 1 }
Write-Host "  PASS" -ForegroundColor Green

# 4. Tests
Write-Host "[4/5] Running Tests..." -ForegroundColor Yellow
python -m pytest tests/ -q --tb=short -k "not test_creates_session and not test_session_happy_path"
if ($LASTEXITCODE -ne 0) { Write-Host "FAIL: Tests failed" -ForegroundColor Red; exit 1 }
Write-Host "  PASS" -ForegroundColor Green

# 5. Frontend Build
Write-Host "[5/5] Frontend Build..." -ForegroundColor Yellow
Push-Location (Join-Path $PSScriptRoot ".." "orion-web")
npx next build
$buildResult = $LASTEXITCODE
Pop-Location
if ($buildResult -ne 0) { Write-Host "FAIL: Frontend build failed" -ForegroundColor Red; exit 1 }
Write-Host "  PASS" -ForegroundColor Green

Write-Host ""
Write-Host "=== All checks passed ===" -ForegroundColor Green
