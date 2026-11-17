param(
    [Parameter(Mandatory)]
    [string]$EngineExe,
    [switch]$Install
)

$ErrorActionPreference = 'Stop'
$exe = Get-Item -LiteralPath $EngineExe
if ($exe.PSIsContainer -or $exe.Extension -ne '.exe') {
    throw 'EngineExe must point to the Engine DJ executable.'
}

if ($Install) {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent().Name
    $principal = New-ScheduledTaskPrincipal -UserId $identity -LogonType Interactive
    $action = New-ScheduledTaskAction -Execute "$PSHOME\powershell.exe" -Argument (
        '-NoProfile -STA -File "{0}" -EngineExe "{1}"' -f $PSCommandPath, $exe.FullName
    )
    $settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew
    Register-ScheduledTask -TaskName 'Engine DJ analysis pilot' -Action $action `
        -Principal $principal -Settings $settings
    return
}

$log = Join-Path $env:LOCALAPPDATA 'EngineDJ-analysis-pilot.log'
function Write-PilotLog([string]$Message) {
    Add-Content -LiteralPath $log -Value ('{0:o} {1}' -f [DateTime]::UtcNow, $Message)
}

try {
    if (Get-Process -Name $exe.BaseName -ErrorAction SilentlyContinue) {
        throw 'Engine DJ is already running. Close it yourself before starting the pilot.'
    }

    Add-Type -AssemblyName System.Windows.Forms
    $engine = Start-Process -FilePath $exe.FullName -WorkingDirectory $exe.DirectoryName -PassThru
    Write-PilotLog "Started Engine PID $($engine.Id). Waiting for operator."

    $answer = [Windows.Forms.MessageBox]::Show(
        'Switch to Engine DJ. When analysis appears finished, return here and click OK to request a normal close. Cancel leaves Engine open.',
        'Engine DJ analysis pilot',
        'OKCancel',
        'Information'
    )
    if ($answer -ne 'OK') {
        throw 'Operator cancelled; no close requested.'
    }

    $engine.Refresh()
    if ($engine.HasExited) {
        throw 'Engine exited before the close request.'
    }
    Write-PilotLog "Requesting window close for PID $($engine.Id)."
    if (-not $engine.CloseMainWindow()) {
        throw 'Engine did not accept a window-close request. Inspect the desktop.'
    }
    if (-not $engine.WaitForExit(60000)) {
        throw 'Engine did not exit within 60 seconds. Inspect the desktop; no force-close attempted.'
    }
    if ($engine.ExitCode -ne 0) {
        throw "Engine exited with code $($engine.ExitCode)."
    }
    Write-PilotLog 'Engine exited normally. Verify the selected database rows separately.'
} catch {
    Write-PilotLog "FAILED: $_"
    throw
}
