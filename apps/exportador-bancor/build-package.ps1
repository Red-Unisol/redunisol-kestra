[CmdletBinding()]
param(
    [string]$PythonExe = "python",
    [switch]$SkipTests
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$pyprojectPath = Join-Path $scriptDir "pyproject.toml"
$readmePath = Join-Path $scriptDir "README.md"
$venvDir = Join-Path $scriptDir ".package-venv"
$venvPython = Join-Path $venvDir "Scripts\python.exe"
$specPath = Join-Path $scriptDir "packaging\pyinstaller\exportador-bancor.spec"
$buildDir = Join-Path $scriptDir "build\pyinstaller"
$distDir = Join-Path $scriptDir "dist"
$pyinstallerDistDir = Join-Path $distDir "pyinstaller"
$stagingDir = Join-Path $distDir "staging"

function Assert-FileExists {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,

        [Parameter(Mandatory = $true)]
        [string]$Label
    )

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Falta $Label en $Path"
    }
}

function Get-ProjectVersion {
    param(
        [Parameter(Mandatory = $true)]
        [string]$PyprojectPath
    )

    foreach ($line in Get-Content -Path $PyprojectPath) {
        if ($line -match '^\s*version\s*=\s*"([^"]+)"\s*$') {
            return $matches[1]
        }
    }

    throw "No se pudo resolver version desde $PyprojectPath"
}

Assert-FileExists -Path $pyprojectPath -Label "pyproject.toml"
Assert-FileExists -Path $readmePath -Label "README.md"
Assert-FileExists -Path $specPath -Label "spec de PyInstaller"

Write-Host "Preparando entorno de build..."
& $PythonExe -m venv $venvDir
if ($LASTEXITCODE -ne 0) {
    throw "Fallo la creacion de la virtualenv de build"
}

Assert-FileExists -Path $venvPython -Label "python de la virtualenv de build"

& $venvPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) {
    throw "Fallo pip install --upgrade pip"
}

& $venvPython -m pip install -e ".[build]"
if ($LASTEXITCODE -ne 0) {
    throw "Fallo pip install -e .[build]"
}

if (-not $SkipTests) {
    Write-Host "Ejecutando tests..."
    Push-Location $scriptDir
    try {
        & $venvPython -m unittest discover -s tests -p "test_*.py"
        if ($LASTEXITCODE -ne 0) {
            throw "Fallo unittest"
        }
    }
    finally {
        Pop-Location
    }
}

$version = Get-ProjectVersion -PyprojectPath $pyprojectPath
$packageName = "exportador-bancor-$version-windows-x86_64"
$packageRoot = Join-Path $stagingDir $packageName
$zipPath = Join-Path $distDir "$packageName.zip"
$builtExePath = Join-Path $pyinstallerDistDir "Exportador Bancor.exe"

if (Test-Path -LiteralPath $buildDir) {
    Remove-Item -LiteralPath $buildDir -Recurse -Force
}
if (Test-Path -LiteralPath $pyinstallerDistDir) {
    Remove-Item -LiteralPath $pyinstallerDistDir -Recurse -Force
}
if (Test-Path -LiteralPath $stagingDir) {
    Remove-Item -LiteralPath $stagingDir -Recurse -Force
}

New-Item -ItemType Directory -Path $buildDir -Force | Out-Null
New-Item -ItemType Directory -Path $pyinstallerDistDir -Force | Out-Null
New-Item -ItemType Directory -Path $packageRoot -Force | Out-Null

Push-Location $scriptDir
try {
    Write-Host "Construyendo ejecutable PyInstaller..."
    & $venvPython -m PyInstaller --noconfirm --clean --distpath $pyinstallerDistDir --workpath $buildDir $specPath
    if ($LASTEXITCODE -ne 0) {
        throw "Fallo PyInstaller"
    }
}
finally {
    Pop-Location
}

Assert-FileExists -Path $builtExePath -Label "ejecutable generado"

Copy-Item -LiteralPath $builtExePath -Destination (Join-Path $packageRoot "Exportador Bancor.exe")
Copy-Item -LiteralPath $readmePath -Destination (Join-Path $packageRoot "README.md")

if (Test-Path -LiteralPath $zipPath) {
    Remove-Item -LiteralPath $zipPath -Force
}

Compress-Archive -Path $packageRoot -DestinationPath $zipPath -CompressionLevel Optimal

Write-Host "Carpeta lista en:"
Write-Host $packageRoot
Write-Host "Zip generado en:"
Write-Host $zipPath
