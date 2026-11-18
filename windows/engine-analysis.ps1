# Engine DJ launch/close task for the Windows guest. Request protocol (files in -ControlDir):
#   host writes  request           a 32-hex token
#   guest writes <token>.started   once Engine is running
#   host writes  <token>.quit      when analysis is saved; guest then requests a normal close
#   guest writes <token>.done      after Engine exits with status 0, else <token>.failed
param(
    [Parameter(Mandatory)]
    [string]$ControlDir,
    [string]$EngineExe = 'C:\Program Files\Engine DJ\Engine DJ.exe',
    [switch]$Install
)

$ErrorActionPreference = 'Stop'
$null = Get-Item -LiteralPath $EngineExe

if ($Install) {
    $local = Join-Path $env:LOCALAPPDATA 'engine-dj-analysis.ps1'
    Copy-Item -LiteralPath $PSCommandPath -Destination $local -Force
    $action = New-ScheduledTaskAction -Execute "$PSHOME\powershell.exe" -Argument (
        '-NoProfile -ExecutionPolicy RemoteSigned -WindowStyle Hidden -File "{0}" -ControlDir "{1}" -EngineExe "{2}"' -f
        $local, $ControlDir, $EngineExe
    )
    $user = [Security.Principal.WindowsIdentity]::GetCurrent().Name
    $principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive
    $trigger = New-ScheduledTaskTrigger -AtLogOn -User $user
    $settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew
    Register-ScheduledTask -TaskName 'Engine DJ analysis' -Action $action -Principal $principal `
        -Trigger $trigger -Settings $settings -Force
    return
}

$request = Join-Path $ControlDir 'request'
$deadline = [DateTime]::UtcNow.AddMinutes(3)
while (-not (Test-Path -LiteralPath $request) -and [DateTime]::UtcNow -lt $deadline) {
    Start-Sleep -Seconds 1
}
if (-not (Test-Path -LiteralPath $request)) { return }

$token = (Get-Content -Raw -LiteralPath $request).Trim()
if ($token -cnotmatch '^[0-9a-f]{32}$') { throw 'Invalid analysis request.' }
$started = Join-Path $ControlDir "$token.started"
$quit = Join-Path $ControlDir "$token.quit"
$done = Join-Path $ControlDir "$token.done"

try {
    $name = [IO.Path]::GetFileNameWithoutExtension($EngineExe)
    if (Get-Process -Name $name -ErrorAction SilentlyContinue) {
        throw 'Engine DJ is already running.'
    }
    $engine = Start-Process -FilePath $EngineExe -WorkingDirectory (Split-Path $EngineExe) -PassThru
    New-Item -ItemType File -Path $started | Out-Null
    while ((Test-Path -LiteralPath $request) -and -not (Test-Path -LiteralPath $quit)) {
        if ($engine.WaitForExit(1000)) { throw 'Engine exited before the close request.' }
    }
    if (-not (Test-Path -LiteralPath $quit)) { throw 'Host withdrew the analysis request.' }
    $engine.Refresh()
    if (-not $engine.CloseMainWindow()) { throw 'Engine did not accept the normal close request.' }
    if (-not $engine.WaitForExit(60000)) { throw 'Engine did not exit within 60 seconds.' }
    if ($engine.ExitCode -ne 0) { throw "Engine exited with code $($engine.ExitCode)." }
    New-Item -ItemType File -Path $done | Out-Null
} catch {
    Set-Content -LiteralPath (Join-Path $ControlDir "$token.failed") -Value "$_"
    throw
}
