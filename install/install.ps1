$ErrorActionPreference = "Stop"

function Fail($Message) {
    Write-Error "error: $Message"
    exit 1
}

function Get-HoloWindowsPlatform {
    $RunningOnWindows = [System.Runtime.InteropServices.RuntimeInformation, mscorlib]::IsOSPlatform(
        [System.Runtime.InteropServices.OSPlatform, mscorlib]::Windows
    )
    if (-not $RunningOnWindows) {
        Fail "Holo Desktop installer does not support this operating system from install.ps1. Use install.sh on macOS or Linux."
    }

    $Architecture = [System.Runtime.InteropServices.RuntimeInformation, mscorlib]::OSArchitecture.ToString()
    switch ($Architecture) {
        "X64" { return "windows-x86_64" }
        "Arm64" { return "windows-arm64" }
        default {
            Fail "Holo Desktop installer does not support Windows architecture '$Architecture'. Supported architectures: X64, Arm64."
        }
    }
}

$Platform = Get-HoloWindowsPlatform
$HoloHome = if ($env:HOLO_HOME) { $env:HOLO_HOME } else { Join-Path $HOME ".holo" }
$ManifestUrl = if ($env:HOLO_INSTALL_MANIFEST_URL) { $env:HOLO_INSTALL_MANIFEST_URL } else { "https://install.hcompany.ai/install/manifest.json" }
$TempRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("holo-install-" + [System.Guid]::NewGuid().ToString("N"))

New-Item -ItemType Directory -Force -Path $TempRoot, (Join-Path $HoloHome "bin"), (Join-Path $HoloHome "toolchain\uv") | Out-Null

try {
    $ManifestPath = Join-Path $TempRoot "manifest.json"
    if ($ManifestUrl.StartsWith("file://")) {
        Copy-Item -Path $ManifestUrl.Substring(7) -Destination $ManifestPath -Force
    } elseif (Test-Path $ManifestUrl) {
        Copy-Item -Path $ManifestUrl -Destination $ManifestPath -Force
    } else {
        Invoke-WebRequest -Uri $ManifestUrl -OutFile $ManifestPath
    }

    $Manifest = Get-Content -Raw $ManifestPath | ConvertFrom-Json
    $Entry = $Manifest.supported_platforms.$Platform
    if ($null -eq $Entry) {
        Fail "installer manifest does not contain $Platform"
    }

    $HoloVersion = [string]$Manifest.holo_version
    $PythonVersion = [string]$Manifest.python_version
    $UvUrl = [string]$Entry.uv_url
    $UvSha256 = [string]$Entry.uv_sha256
    $PackageSpec = if ($env:HOLO_INSTALL_PACKAGE) { $env:HOLO_INSTALL_PACKAGE } else { "holo-desktop-cli==$HoloVersion" }

    $UvZip = Join-Path $TempRoot "uv.zip"
    if ($UvUrl.StartsWith("file://")) {
        Copy-Item -Path $UvUrl.Substring(7) -Destination $UvZip -Force
    } elseif (Test-Path $UvUrl) {
        Copy-Item -Path $UvUrl -Destination $UvZip -Force
    } else {
        Invoke-WebRequest -Uri $UvUrl -OutFile $UvZip
    }

    $ActualSha256 = (Get-FileHash -Algorithm SHA256 -Path $UvZip).Hash.ToLowerInvariant()
    if ($ActualSha256 -ne $UvSha256.ToLowerInvariant()) {
        Fail "sha256 mismatch for uv: expected $UvSha256, got $ActualSha256"
    }

    $ExtractDir = Join-Path $TempRoot "uv"
    Expand-Archive -Path $UvZip -DestinationPath $ExtractDir -Force
    $UvFound = Get-ChildItem -Path $ExtractDir -Recurse -Filter "uv.exe" | Select-Object -First 1
    if ($null -eq $UvFound) {
        Fail "downloaded uv archive did not contain uv.exe"
    }

    $UvExe = Join-Path $HoloHome "toolchain\uv\uv.exe"
    Copy-Item -Path $UvFound.FullName -Destination $UvExe -Force

    $env:UV_PYTHON_INSTALL_DIR = Join-Path $HoloHome "python"
    $env:UV_TOOL_DIR = Join-Path $HoloHome "tools"
    $env:UV_TOOL_BIN_DIR = Join-Path $HoloHome "bin"

    & $UvExe python install $PythonVersion --no-bin --no-registry
    if ($LASTEXITCODE -ne 0) {
        Fail "uv failed to install Python $PythonVersion"
    }

    $PythonExe = (& $UvExe python find --managed-python $PythonVersion).Trim()
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $PythonExe)) {
        Fail "uv installed Python $PythonVersion but could not resolve its executable"
    }
    $PythonMachine = (& $PythonExe -c "import platform; print(platform.machine())").Trim().ToUpperInvariant()
    if ($LASTEXITCODE -ne 0) {
        Fail "installed Python could not report its machine architecture"
    }
    $ExpectedPythonMachine = switch ($Platform) {
        "windows-x86_64" { "AMD64" }
        "windows-arm64" { "ARM64" }
        default { Fail "installer has no Python architecture contract for $Platform" }
    }
    if ($PythonMachine -ne $ExpectedPythonMachine) {
        Fail "installed Python architecture '$PythonMachine' does not match $Platform (expected $ExpectedPythonMachine)"
    }

    & $UvExe tool install $PackageSpec --python $PythonExe --force --reinstall-package holo-desktop-cli
    if ($LASTEXITCODE -ne 0) {
        Fail "uv failed to install $PackageSpec with $PythonExe"
    }

    $BinDir = Join-Path $HoloHome "bin"
    $UserPath = [Environment]::GetEnvironmentVariable("Path", "User")
    $Parts = @()
    if ($UserPath) {
        $Parts = $UserPath -split ";"
    }
    if ($Parts -notcontains $BinDir) {
        $NewPath = if ($UserPath) { "$BinDir;$UserPath" } else { $BinDir }
        [Environment]::SetEnvironmentVariable("Path", $NewPath, "User")
    }

    if ($env:HOLO_INSTALL_SKIP_RUN_SETUP -ne "1") {
        & $UvExe run --python $PythonExe --with $PackageSpec python -m holo_desktop.installer_bootstrap --yes
        if ($LASTEXITCODE -ne 0) {
            Fail "Holo Desktop runtime setup failed"
        }
    }

    Write-Host ""
    Write-Host "Holo installed."
    Write-Host "Open a new PowerShell window, then run:"
    Write-Host "  holo login"
    Write-Host "  holo run `"Open Calculator and compute 2+2`""
} finally {
    Remove-Item -Recurse -Force $TempRoot -ErrorAction SilentlyContinue
}
