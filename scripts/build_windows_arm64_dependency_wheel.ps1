[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$WheelDirectory,

    [Parameter(Mandatory = $true)]
    [string]$ManifestOutput,

    [string]$WheelBaseUrl = "https://install.hcompany.ai/wheels/windows-arm64"
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path $PSScriptRoot -Parent
$ManifestSource = Join-Path $RepoRoot "install\manifest.json"
$Manifest = Get-Content -Raw $ManifestSource | ConvertFrom-Json
$WindowsArm64 = $Manifest.supported_platforms."windows-arm64"
$Dependencies = @($WindowsArm64.dependency_wheels)

if ($Dependencies.Count -ne 1 -or [string]$Dependencies[0].name -ne "cryptography") {
    throw "Windows ARM64 manifest must contain exactly one cryptography dependency wheel"
}

$Dependency = $Dependencies[0]
$DependencyName = [string]$Dependency.name
$DependencyVersion = [string]$Dependency.version
$PythonVersion = [string]$Manifest.python_version
$VcpkgRoot = $env:VCPKG_INSTALLATION_ROOT

if (-not $VcpkgRoot -or -not (Test-Path (Join-Path $VcpkgRoot "vcpkg.exe"))) {
    throw "VCPKG_INSTALLATION_ROOT does not point to a vcpkg installation"
}

New-Item -ItemType Directory -Force -Path $WheelDirectory | Out-Null
if (Get-ChildItem -Path $WheelDirectory -Filter "*.whl" -ErrorAction SilentlyContinue) {
    throw "wheel output directory must not already contain wheel files: $WheelDirectory"
}

& (Join-Path $VcpkgRoot "vcpkg.exe") install openssl:arm64-windows-static-md
if ($LASTEXITCODE -ne 0) {
    throw "vcpkg failed to install OpenSSL for Windows ARM64"
}

$env:VCPKG_ROOT = $VcpkgRoot
$env:OPENSSL_DIR = Join-Path $VcpkgRoot "installed\arm64-windows-static-md"
$env:OPENSSL_STATIC = "1"

& uv python install $PythonVersion --no-bin --no-registry
if ($LASTEXITCODE -ne 0) {
    throw "uv failed to install Python $PythonVersion"
}

& uv run --no-project --python $PythonVersion --with pip python -m pip wheel `
    "$DependencyName==$DependencyVersion" `
    --no-deps `
    --no-binary $DependencyName `
    --no-cache-dir `
    --wheel-dir $WheelDirectory
if ($LASTEXITCODE -ne 0) {
    throw "failed to build $DependencyName $DependencyVersion for Windows ARM64"
}

$Wheels = @(Get-ChildItem -Path $WheelDirectory -Filter "$DependencyName-*-win_arm64.whl")
if ($Wheels.Count -ne 1) {
    $Found = @(Get-ChildItem -Path $WheelDirectory -Filter "*.whl" | ForEach-Object Name) -join ", "
    throw "expected one Windows ARM64 $DependencyName wheel, found: $Found"
}

$Wheel = $Wheels[0]
$WheelSha256 = (Get-FileHash -Algorithm SHA256 -Path $Wheel.FullName).Hash.ToLowerInvariant()
$Dependency.url = if ($WheelBaseUrl -match "^https?://") {
    "$($WheelBaseUrl.TrimEnd('/'))/$DependencyName/$DependencyVersion/$($Wheel.Name)"
} else {
    Join-Path $WheelBaseUrl $Wheel.Name
}
$Dependency.sha256 = $WheelSha256

$ManifestParent = Split-Path $ManifestOutput -Parent
if ($ManifestParent) {
    New-Item -ItemType Directory -Force -Path $ManifestParent | Out-Null
}
$Manifest | ConvertTo-Json -Depth 10 | Set-Content -Path $ManifestOutput -Encoding utf8

if ($env:GITHUB_OUTPUT) {
    @(
        "wheel_path=$($Wheel.FullName)"
        "wheel_name=$($Wheel.Name)"
        "wheel_sha256=$WheelSha256"
        "manifest_path=$ManifestOutput"
    ) | Out-File -FilePath $env:GITHUB_OUTPUT -Encoding utf8 -Append
}

Write-Host "wheel_path=$($Wheel.FullName)"
Write-Host "wheel_sha256=$WheelSha256"
Write-Host "manifest_path=$ManifestOutput"
