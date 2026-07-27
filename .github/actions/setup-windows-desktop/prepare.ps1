$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$artifactDirectory = Join-Path $env:RUNNER_TEMP "holo-windows-desktop-readiness"
$readinessPath = Join-Path $artifactDirectory "windows-desktop-readiness.json"
$processesPath = Join-Path $artifactDirectory "processes.json"
$windowsPath = Join-Path $artifactDirectory "windows.json"
$appProbesPath = Join-Path $artifactDirectory "app-probes.json"
$screenshotPath = Join-Path $artifactDirectory "desktop-ready.png"
$initialWindowsPath = Join-Path $artifactDirectory "windows-before.json"
$initialProcessesPath = Join-Path $artifactDirectory "processes-before.json"
$normalizationLogPath = Join-Path $artifactDirectory "normalization.log"

New-Item -ItemType Directory -Path $artifactDirectory -Force | Out-Null
"artifact-path=$artifactDirectory" | Out-File -FilePath $env:GITHUB_OUTPUT -Encoding utf8 -Append

Start-Transcript -Path $normalizationLogPath -Force | Out-Null

Add-Type -TypeDefinition @"
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Text;

namespace HoloE2E {
    public sealed class WindowSnapshot {
        public long Handle { get; set; }
        public int ProcessId { get; set; }
        public string Title { get; set; } = "";
        public string ClassName { get; set; } = "";
        public bool Visible { get; set; }
        public bool Hung { get; set; }
    }

    public static class NativeWindows {
        private delegate bool EnumWindowsProc(IntPtr handle, IntPtr parameter);

        [DllImport("user32.dll")]
        private static extern bool EnumWindows(EnumWindowsProc callback, IntPtr parameter);

        [DllImport("user32.dll", CharSet = CharSet.Unicode)]
        private static extern int GetWindowText(IntPtr handle, StringBuilder text, int maximumCount);

        [DllImport("user32.dll", CharSet = CharSet.Unicode)]
        private static extern int GetClassName(IntPtr handle, StringBuilder text, int maximumCount);

        [DllImport("user32.dll")]
        private static extern uint GetWindowThreadProcessId(IntPtr handle, out uint processId);

        [DllImport("user32.dll")]
        private static extern bool IsWindowVisible(IntPtr handle);

        [DllImport("user32.dll")]
        private static extern bool IsHungAppWindow(IntPtr handle);

        [DllImport("user32.dll")]
        private static extern IntPtr GetForegroundWindow();

        [DllImport("user32.dll")]
        private static extern bool SetForegroundWindow(IntPtr handle);

        [DllImport("user32.dll")]
        private static extern bool ShowWindowAsync(IntPtr handle, int command);

        [DllImport("user32.dll")]
        private static extern bool PostMessage(IntPtr handle, uint message, IntPtr wordParameter, IntPtr longParameter);

        public static WindowSnapshot[] EnumerateWindows() {
            var windows = new List<WindowSnapshot>();
            EnumWindows(delegate(IntPtr handle, IntPtr parameter) {
                uint processId;
                GetWindowThreadProcessId(handle, out processId);
                var title = new StringBuilder(1024);
                var className = new StringBuilder(256);
                GetWindowText(handle, title, title.Capacity);
                GetClassName(handle, className, className.Capacity);
                windows.Add(new WindowSnapshot {
                    Handle = handle.ToInt64(),
                    ProcessId = checked((int)processId),
                    Title = title.ToString(),
                    ClassName = className.ToString(),
                    Visible = IsWindowVisible(handle),
                    Hung = IsHungAppWindow(handle)
                });
                return true;
            }, IntPtr.Zero);
            return windows.ToArray();
        }

        public static long ForegroundHandle() {
            return GetForegroundWindow().ToInt64();
        }

        public static bool Activate(long handle) {
            var window = new IntPtr(handle);
            ShowWindowAsync(window, 5);
            return SetForegroundWindow(window);
        }

        public static bool Hide(long handle) {
            return ShowWindowAsync(new IntPtr(handle), 0);
        }

        public static bool Close(long handle) {
            return PostMessage(new IntPtr(handle), 0x0010, IntPtr.Zero, IntPtr.Zero);
        }
    }
}
"@
Add-Type -AssemblyName UIAutomationClient

function Get-HoloWindowSnapshot {
    $foregroundHandle = [HoloE2E.NativeWindows]::ForegroundHandle()
    $windows = foreach ($window in [HoloE2E.NativeWindows]::EnumerateWindows()) {
        $process = Get-Process -Id $window.ProcessId -ErrorAction SilentlyContinue
        [pscustomobject]@{
            handle = "0x{0:X}" -f $window.Handle
            handle_value = $window.Handle
            process_id = $window.ProcessId
            process_name = if ($null -ne $process) { $process.ProcessName } else { $null }
            title = $window.Title
            class_name = $window.ClassName
            visible = $window.Visible
            hung = $window.Hung
            foreground = $window.Handle -eq $foregroundHandle
        }
    }
    return @($windows)
}

function Write-HoloJson {
    param(
        [Parameter(Mandatory = $true)] [object] $Value,
        [Parameter(Mandatory = $true)] [string] $Path
    )
    $Value | ConvertTo-Json -Depth 6 | Set-Content -Path $Path -Encoding utf8
}

function Write-HoloProcessSnapshot {
    param([Parameter(Mandatory = $true)] [string] $Path)
    $processes = Get-Process |
        Sort-Object ProcessName, Id |
        Select-Object ProcessName, Id, MainWindowTitle, Responding
    Write-HoloJson -Value @($processes) -Path $Path
}

function Set-HoloDwordPolicy {
    param(
        [Parameter(Mandatory = $true)] [string] $Path,
        [Parameter(Mandatory = $true)] [string] $Name,
        [Parameter(Mandatory = $true)] [int] $Value
    )
    New-Item -Path $Path -Force | Out-Null
    New-ItemProperty -Path $Path -Name $Name -PropertyType DWord -Value $Value -Force | Out-Null
    Write-Host "Set policy $Path\$Name=$Value"
}

function Stop-HoloFirstRunProcesses {
    foreach ($processName in @(
            "msedge",
            "SystemSettings",
            "notepad",
            "CalculatorApp",
            "calc"
        )) {
        Get-Process -Name $processName -ErrorAction SilentlyContinue |
            Stop-Process -Force -ErrorAction SilentlyContinue
    }
}

function Close-HoloBlockingWindows {
    foreach ($window in Get-HoloWindowSnapshot | Where-Object { $_.visible }) {
        if ($window.process_name -eq "wsl") {
            Write-Host "Hiding WSL provisioning console $($window.handle)"
            [void][HoloE2E.NativeWindows]::Hide([long]$window.handle_value)
        }
    }
}

function Restart-HoloExplorer {
    Get-Process -Name explorer -ErrorAction SilentlyContinue |
        Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 1
    Start-Process -FilePath "$env:WINDIR\explorer.exe" -ArgumentList "shell:desktop"
}

function Test-HoloPrivacyExperience {
    try {
        $root = [System.Windows.Automation.AutomationElement]::RootElement
        $elements = $root.FindAll(
            [System.Windows.Automation.TreeScope]::Descendants,
            [System.Windows.Automation.Condition]::TrueCondition
        )
        foreach ($element in $elements) {
            $name = $element.Current.Name
            if ($name -match "(?i)choose privacy settings for your device|privacy settings for your device") {
                return $true
            }
        }
        return $false
    } catch {
        Write-Warning "UI Automation desktop probe failed: $($_.Exception.GetType().Name): $($_.Exception.Message)"
        return $null
    }
}

function Complete-HoloPrivacyExperience {
    $oobeWindows = @(
        Get-HoloWindowSnapshot |
            Where-Object { $_.visible -and $_.class_name -eq "Shell_OOBEProxy" }
    )
    if ($oobeWindows.Count -eq 0 -and (Test-HoloPrivacyExperience) -ne $true) {
        Write-Host "Privacy OOBE proxy is absent; no semantic completion is required."
        return $false
    }

    Write-Host "Privacy OOBE proxy is visible; completing its Next/Accept sequence through UI Automation."
    $deadline = [DateTimeOffset]::UtcNow.AddSeconds(120)
    $invocationCount = 0
    do {
        $oobeWindows = @(
            Get-HoloWindowSnapshot |
                Where-Object { $_.visible -and $_.class_name -eq "Shell_OOBEProxy" }
        )
        $privacyExperienceVisible = Test-HoloPrivacyExperience
        if ($oobeWindows.Count -eq 0 -and $privacyExperienceVisible -eq $false) {
            Write-Host "Privacy OOBE proxy disappeared after semantic completion."
            return $true
        }

        try {
            $root = [System.Windows.Automation.AutomationElement]::RootElement
            $elements = $root.FindAll(
                [System.Windows.Automation.TreeScope]::Descendants,
                [System.Windows.Automation.Condition]::TrueCondition
            )
            $navigationButton = $null
            foreach ($wantedName in @("Accept", "Next")) {
                foreach ($element in $elements) {
                    if (
                        $element.Current.ControlType -eq [System.Windows.Automation.ControlType]::Button -and
                        $element.Current.IsEnabled -and
                        $element.Current.Name -match "^(?i:$wantedName)$"
                    ) {
                        $navigationButton = $element
                        break
                    }
                }
                if ($null -ne $navigationButton) {
                    break
                }
            }
            if ($null -ne $navigationButton) {
                $buttonName = $navigationButton.Current.Name
                $invokePattern = $navigationButton.GetCurrentPattern(
                    [System.Windows.Automation.InvokePattern]::Pattern
                )
                $invokePattern.Invoke()
                $invocationCount += 1
                Write-Host "Invoked privacy OOBE button '$buttonName' through UI Automation."
                Start-Sleep -Seconds 2
                continue
            }
        } catch {
            Write-Warning "Privacy OOBE UI Automation pass failed: $($_.Exception.GetType().Name): $($_.Exception.Message)"
        }

        Write-Host "Waiting for the privacy OOBE navigation controls to become available."
        Start-Sleep -Seconds 2
    } while (
        [DateTimeOffset]::UtcNow -lt $deadline -and
        $invocationCount -lt 10
    )

    Write-Warning (
        "Privacy OOBE did not complete naturally after {0} semantic navigation invocation(s)." -f
        $invocationCount
    )
    return $false
}

function Assert-HoloPrivacyExperienceCompleted {
    $oobeWindows = @(
        Get-HoloWindowSnapshot |
            Where-Object { $_.visible -and $_.class_name -eq "Shell_OOBEProxy" }
    )
    $privacyExperienceVisible = Test-HoloPrivacyExperience
    if ($oobeWindows.Count -gt 0 -or $privacyExperienceVisible -ne $false) {
        throw (
            "Privacy OOBE completion could not be proven: proxy_windows={0}, semantic_visible={1}" -f
            $oobeWindows.Count,
            $privacyExperienceVisible
        )
    }
    Write-Host "Privacy OOBE natural completion is proven."
}

function Set-HoloExplorerForeground {
    $windows = Get-HoloWindowSnapshot
    $candidate = $windows |
        Where-Object {
            $_.visible -and
            $_.process_name -eq "explorer" -and
            $_.class_name -in @("CabinetWClass", "Shell_TrayWnd", "Progman", "WorkerW")
        } |
        Sort-Object @{ Expression = { if ($_.class_name -eq "CabinetWClass") { 0 } else { 1 } } } |
        Select-Object -First 1
    if ($null -ne $candidate) {
        [void][HoloE2E.NativeWindows]::Activate([long]$candidate.handle_value)
    }
}

function Get-HoloDesktopState {
    $windows = Get-HoloWindowSnapshot
    $visibleWindows = @($windows | Where-Object { $_.visible })
    $foreground = $windows | Where-Object { $_.foreground } | Select-Object -First 1
    $explorerWindows = @(
        $visibleWindows |
            Where-Object {
                $_.process_name -eq "explorer" -and
                $_.class_name -in @("CabinetWClass", "Shell_TrayWnd", "Progman", "WorkerW")
            }
    )
    $oobeWindows = @(
        $visibleWindows |
            Where-Object {
                $_.class_name -eq "Shell_OOBEProxy" -or
                $_.title -match "(?i)choose privacy settings|privacy settings for your device"
            }
    )
    $privacyExperienceVisible = Test-HoloPrivacyExperience

    $blockers = [System.Collections.Generic.List[string]]::new()
    if (
        (Get-Process -Name UserOOBEBroker -ErrorAction SilentlyContinue) -or
        $oobeWindows.Count -gt 0 -or
        $privacyExperienceVisible -eq $true
    ) {
        [void]$blockers.Add("privacy_oobe")
    }
    if ($null -eq $privacyExperienceVisible) {
        [void]$blockers.Add("desktop_oracle_unavailable")
    }
    if ($visibleWindows | Where-Object { $_.process_name -eq "msedge" }) {
        [void]$blockers.Add("edge_first_run")
    }
    if ($visibleWindows | Where-Object {
            $_.process_name -eq "wsl" -or
            $_.title -match "(?i)Windows Subsystem for Linux|WSL update|install WSL"
        }) {
        [void]$blockers.Add("wsl_prompt")
    }
    if ($explorerWindows.Count -eq 0) {
        [void]$blockers.Add("explorer_missing")
    } elseif ($explorerWindows | Where-Object { $_.hung }) {
        [void]$blockers.Add("explorer_unresponsive")
    }
    if ($null -eq $foreground -or $foreground.process_name -ne "explorer") {
        [void]$blockers.Add("unexpected_foreground_app")
    }

    [pscustomobject]@{
        blockers = @($blockers | Select-Object -Unique)
        windows = $windows
        foreground_process = if ($null -ne $foreground) { $foreground.process_name } else { $null }
        foreground_title = if ($null -ne $foreground) { $foreground.title } else { $null }
        explorer_responsive = $explorerWindows.Count -gt 0 -and -not ($explorerWindows | Where-Object { $_.hung })
    }
}

function Wait-HoloDesktopReady {
    param([int] $TimeoutSeconds = 120)
    $deadline = [DateTimeOffset]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        Close-HoloBlockingWindows
        Set-HoloExplorerForeground
        Start-Sleep -Milliseconds 500
        $state = Get-HoloDesktopState
        if ($state.blockers.Count -eq 0) {
            return $state
        }
        Write-Host "Desktop blockers: $($state.blockers -join ', ')"
        Start-Sleep -Seconds 2
    } while ([DateTimeOffset]::UtcNow -lt $deadline)
    return $state
}

function Save-HoloScreenshot {
    param([Parameter(Mandatory = $true)] [string] $Path)
    try {
        Add-Type -AssemblyName System.Windows.Forms
        Add-Type -AssemblyName System.Drawing
        $bounds = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
        $bitmap = [System.Drawing.Bitmap]::new($bounds.Width, $bounds.Height)
        try {
            $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
            try {
                $graphics.CopyFromScreen($bounds.Location, [System.Drawing.Point]::Empty, $bounds.Size)
            } finally {
                $graphics.Dispose()
            }
            $bitmap.Save($Path, [System.Drawing.Imaging.ImageFormat]::Png)
        } finally {
            $bitmap.Dispose()
        }
        return (Test-Path $Path) -and (Get-Item $Path).Length -gt 0
    } catch {
        Write-Warning "Screenshot capture failed: $($_.Exception.GetType().Name): $($_.Exception.Message)"
        return $false
    }
}

function Invoke-HoloAppProbe {
    param(
        [Parameter(Mandatory = $true)] [string] $Name,
        [Parameter(Mandatory = $true)] [scriptblock] $Start,
        [Parameter(Mandatory = $true)] [scriptblock] $WindowMatches
    )
    $startedAt = [DateTimeOffset]::UtcNow
    & $Start
    $deadline = [DateTimeOffset]::UtcNow.AddSeconds(20)
    do {
        Start-Sleep -Milliseconds 500
        $matchingWindows = @(Get-HoloWindowSnapshot | Where-Object $WindowMatches)
        if ($matchingWindows.Count -gt 0) {
            return [pscustomobject]@{
                name = $Name
                passed = $true
                duration_s = [Math]::Round(([DateTimeOffset]::UtcNow - $startedAt).TotalSeconds, 3)
                windows = $matchingWindows
            }
        }
    } while ([DateTimeOffset]::UtcNow -lt $deadline)
    return [pscustomobject]@{
        name = $Name
        passed = $false
        duration_s = [Math]::Round(([DateTimeOffset]::UtcNow - $startedAt).TotalSeconds, 3)
        windows = @()
    }
}

function Invoke-HoloAppProbes {
    $results = @()
    $results += Invoke-HoloAppProbe -Name "Notepad" `
        -Start { Start-Process -FilePath "notepad.exe" } `
        -WindowMatches { $_.visible -and ($_.process_name -like "notepad*" -or $_.title -match "(?i)Notepad") }
    Get-Process -Name notepad -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue

    $results += Invoke-HoloAppProbe -Name "Calculator" `
        -Start { Start-Process -FilePath "calc.exe" } `
        -WindowMatches {
            $_.visible -and
            ($_.process_name -in @("CalculatorApp", "ApplicationFrameHost") -or $_.title -match "(?i)Calculator")
        }
    foreach ($processName in @("CalculatorApp", "calc")) {
        Get-Process -Name $processName -ErrorAction SilentlyContinue |
            Stop-Process -Force -ErrorAction SilentlyContinue
    }

    $results += Invoke-HoloAppProbe -Name "File Explorer" `
        -Start { Start-Process -FilePath "$env:WINDIR\explorer.exe" -ArgumentList "shell:desktop" } `
        -WindowMatches {
            $_.visible -and
            $_.process_name -eq "explorer" -and
            $_.class_name -eq "CabinetWClass" -and
            -not $_.hung
        }
    return @($results)
}

function Write-HoloReadiness {
    param(
        [Parameter(Mandatory = $true)] [object] $State,
        [Parameter(Mandatory = $true)] [AllowEmptyCollection()] [string[]] $Blockers,
        [Parameter(Mandatory = $true)] [bool] $ScreenshotAvailable
    )
    Write-HoloJson -Value $State.windows -Path $windowsPath
    Write-HoloProcessSnapshot -Path $processesPath
    $payload = [ordered]@{
        schema_version = 1
        ready = $Blockers.Count -eq 0
        blockers = @($Blockers)
        os_version = [System.Environment]::OSVersion.Version.ToString()
        architecture = [System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture.ToString().ToUpperInvariant()
        foreground_process = $State.foreground_process
        foreground_title = $State.foreground_title
        explorer_responsive = [bool]$State.explorer_responsive
        screenshot_path = if ($ScreenshotAvailable) { Split-Path -Leaf $screenshotPath } else { $null }
        processes_path = Split-Path -Leaf $processesPath
        windows_path = Split-Path -Leaf $windowsPath
        app_probes_path = Split-Path -Leaf $appProbesPath
    }
    Write-HoloJson -Value $payload -Path $readinessPath
    Write-Host ($payload | ConvertTo-Json -Depth 6)
}

$finalState = $null
$finalBlockers = @()
$screenshotAvailable = $false

try {
    Write-HoloJson -Value (Get-HoloWindowSnapshot) -Path $initialWindowsPath
    Write-HoloProcessSnapshot -Path $initialProcessesPath

    Set-HoloDwordPolicy `
        -Path "HKLM:\SOFTWARE\Policies\Microsoft\Windows\OOBE" `
        -Name "DisablePrivacyExperience" `
        -Value 1
    Set-HoloDwordPolicy `
        -Path "HKCU:\SOFTWARE\Policies\Microsoft\Windows\OOBE" `
        -Name "DisablePrivacyExperience" `
        -Value 1
    Set-HoloDwordPolicy `
        -Path "HKLM:\SOFTWARE\Policies\Microsoft\Edge" `
        -Name "HideFirstRunExperience" `
        -Value 1

    [void](Complete-HoloPrivacyExperience)
    Assert-HoloPrivacyExperienceCompleted
    Stop-HoloFirstRunProcesses
    Restart-HoloExplorer
    $initialReadyState = Wait-HoloDesktopReady

    if ($initialReadyState.blockers.Count -gt 0) {
        $finalState = $initialReadyState
        $finalBlockers += @($initialReadyState.blockers)
        Write-HoloJson -Value @() -Path $appProbesPath
    } else {
        $probeApps = $env:HOLO_WINDOWS_PROBE_APPS -eq "true"
        if ($probeApps) {
            $appProbeResults = Invoke-HoloAppProbes
        } else {
            $appProbeResults = @()
        }
        Write-HoloJson -Value @($appProbeResults) -Path $appProbesPath

        Stop-HoloFirstRunProcesses
        Restart-HoloExplorer
        $settleSeconds = [int]$env:HOLO_WINDOWS_SETTLE_SECONDS
        if ($settleSeconds -gt 0) {
            Start-Sleep -Seconds $settleSeconds
        }
        $finalState = Wait-HoloDesktopReady
        $finalBlockers += @($finalState.blockers)
        if ($probeApps -and ($appProbeResults | Where-Object { -not $_.passed })) {
            $finalBlockers += "app_probe_failed"
        }
    }

    $observedArchitecture = [System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture.ToString()
    if ($observedArchitecture -ne $env:HOLO_WINDOWS_EXPECTED_ARCHITECTURE) {
        $finalBlockers += "architecture_mismatch"
    }

    $screenshotAvailable = Save-HoloScreenshot -Path $screenshotPath
    if (-not $screenshotAvailable) {
        $finalBlockers += "screenshot_unavailable"
    }
} catch {
    Write-Error -ErrorRecord $_
    $finalBlockers += "normalization_failed"
    if ($null -eq $finalState) {
        $finalState = Get-HoloDesktopState
    }
    if (-not (Test-Path $appProbesPath)) {
        Write-HoloJson -Value @() -Path $appProbesPath
    }
    $screenshotAvailable = Save-HoloScreenshot -Path $screenshotPath
    if (-not $screenshotAvailable) {
        $finalBlockers += "screenshot_unavailable"
    }
} finally {
    if ($null -eq $finalState) {
        $finalState = Get-HoloDesktopState
    }
    Write-HoloReadiness `
        -State $finalState `
        -Blockers @($finalBlockers | Select-Object -Unique) `
        -ScreenshotAvailable $screenshotAvailable
    Stop-Transcript | Out-Null
}

if ($finalBlockers.Count -gt 0) {
    throw "Windows desktop readiness failed: $(@($finalBlockers | Select-Object -Unique) -join ', ')"
}
