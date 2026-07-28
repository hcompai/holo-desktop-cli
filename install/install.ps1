$ErrorActionPreference = "Stop"

function Fail($Message) {
    Write-Error "error: $Message"
    exit 1
}

function Copy-OrDownloadArtifact($Source, $Destination) {
    if ($Source.StartsWith("file://")) {
        Copy-Item -Path $Source.Substring(7) -Destination $Destination -Force
    } elseif (Test-Path $Source) {
        Copy-Item -Path $Source -Destination $Destination -Force
    } else {
        Invoke-WebRequest -Uri $Source -OutFile $Destination
    }
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
    Copy-OrDownloadArtifact $ManifestUrl $ManifestPath

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
    Copy-OrDownloadArtifact $UvUrl $UvZip

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

    $BinaryDependencyArgs = @()
    if ($Platform -eq "windows-arm64") {
        $WheelDirectory = Join-Path $TempRoot "wheels"
        New-Item -ItemType Directory -Force -Path $WheelDirectory | Out-Null
        $Dependencies = @($Entry.dependency_wheels)
        if ($Dependencies.Count -eq 0) {
            Fail "installer manifest does not contain Windows ARM64 dependency wheels"
        }
        foreach ($Dependency in $Dependencies) {
            $DependencyName = [string]$Dependency.name
            $DependencyUrl = [string]$Dependency.url
            $DependencySha256 = [string]$Dependency.sha256
            if (-not $DependencyName -or -not $DependencyUrl -or $DependencyUrl -eq "BUILD_AT_RELEASE") {
                Fail "installer manifest has an unpublished Windows ARM64 dependency wheel"
            }
            if ($DependencySha256 -notmatch "^[0-9a-fA-F]{64}$" -or $DependencySha256 -match "^0{64}$") {
                Fail "installer manifest has an invalid SHA for Windows ARM64 dependency '$DependencyName'"
            }

            $DependencyFileName = if ($DependencyUrl -match "^[a-zA-Z][a-zA-Z0-9+.-]*://") {
                Split-Path ([System.Uri]$DependencyUrl).AbsolutePath -Leaf
            } else {
                Split-Path $DependencyUrl -Leaf
            }
            if (-not $DependencyFileName.EndsWith(".whl")) {
                Fail "Windows ARM64 dependency '$DependencyName' URL does not name a wheel: $DependencyUrl"
            }
            $DependencyPath = Join-Path $WheelDirectory $DependencyFileName
            Copy-OrDownloadArtifact $DependencyUrl $DependencyPath
            $ActualDependencySha256 = (Get-FileHash -Algorithm SHA256 -Path $DependencyPath).Hash.ToLowerInvariant()
            if ($ActualDependencySha256 -ne $DependencySha256.ToLowerInvariant()) {
                Fail "sha256 mismatch for Windows ARM64 dependency '$DependencyName': expected $DependencySha256, got $ActualDependencySha256"
            }
        }
        $BinaryDependencyArgs = @("--find-links", $WheelDirectory, "--no-build")
    }

    & $UvExe tool install $PackageSpec --python $PythonExe --force --reinstall-package holo-desktop-cli @BinaryDependencyArgs
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
        & $UvExe run --python $PythonExe --with $PackageSpec @BinaryDependencyArgs python -m holo_desktop.installer_bootstrap --yes
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
