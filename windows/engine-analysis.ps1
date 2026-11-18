# Engine DJ launch/close task for the Windows guest. Request protocol (files in -ControlDir):
#   host writes  request           a 32-hex token
#   guest writes <token>.started   once Engine is running
#   host writes  <token>.quit      when analysis is saved; guest then quits Engine
#   guest writes <token>.done      after Engine exits with status 0, else <token>.failed
# Engine's prompts are answered through Windows UI Automation. Only the listed notices are
# dismissed; any other dialog fails the run with its text in <token>.failed.
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

Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes
$AE = [Windows.Automation.AutomationElement]
$Descendants = [Windows.Automation.TreeScope]::Descendants

# Notices that only need OK; their text is matched as a prefix.
$Notices = @(
    'C: is incompatible with Engine OS devices',
    'Mono output devices are not supported'
)

function Find-ById($root, [string]$id) {
    $root.FindFirst($Descendants, (New-Object Windows.Automation.PropertyCondition($AE::AutomationIdProperty, $id)))
}

function Invoke-Button($root, [string]$id, [string]$name) {
    $condition = New-Object Windows.Automation.AndCondition(
        (New-Object Windows.Automation.PropertyCondition($AE::AutomationIdProperty, $id)),
        (New-Object Windows.Automation.PropertyCondition($AE::NameProperty, $name))
    )
    $button = $root.FindFirst($Descendants, $condition)
    if ($null -eq $button) { return $false }
    $button.GetCurrentPattern([Windows.Automation.InvokePattern]::Pattern).Invoke()
    $true
}

# Answers whatever prompt Engine is showing. Returns normally when there is none.
function Resolve-Dialogs($engine, [bool]$quitting) {
    $engine.Refresh()
    if ($engine.MainWindowHandle -eq 0) { return }
    try {
        $root = $AE::FromHandle($engine.MainWindowHandle)
        if ($null -ne (Find-ById $root 'QuitDialogBox_Label')) {
            if ($quitting) { $null = Invoke-Button $root 'QuitDialogBoxDialogButtonBox.Button' 'YES' }
            else { $unexpected = 'Engine asked to quit before it was told to' }
        }
        else {
            $box = Find-ById $root 'DialogBox.DialogButtonBox'
            if ($null -ne $box) {
                $window = [Windows.Automation.TreeWalker]::ControlViewWalker.GetParent($box)
                if ($null -eq $window) { $window = $root }
                $texts = $window.FindAll($Descendants, (New-Object Windows.Automation.PropertyCondition(
                    $AE::ControlTypeProperty, [Windows.Automation.ControlType]::Text))) |
                    ForEach-Object { $_.Current.Name } | Where-Object { $_ -and $_ -ne 'OK' }
                $message = $texts -join ' / '
                if ($Notices | Where-Object { $message.StartsWith($_) }) {
                    $null = Invoke-Button $root 'DialogBox.DialogButtonBox.Button' 'OK'
                }
                else { $unexpected = "Unexpected Engine dialog: $message" }
            }
        }
    }
    catch [Windows.Automation.ElementNotAvailableException] { return }
    if ($unexpected) { throw $unexpected }
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
        if ($engine.WaitForExit(500)) { throw 'Engine exited before the close request.' }
        Resolve-Dialogs $engine $false
    }
    if (-not (Test-Path -LiteralPath $quit)) { throw 'Host withdrew the analysis request.' }
    if (-not $engine.CloseMainWindow()) { throw 'Engine did not accept the normal close request.' }
    $limit = [DateTime]::UtcNow.AddSeconds(60)
    while (-not $engine.WaitForExit(500)) {
        if ([DateTime]::UtcNow -ge $limit) { throw 'Engine did not exit within 60 seconds.' }
        Resolve-Dialogs $engine $true
    }
    if ($engine.ExitCode -ne 0) { throw "Engine exited with code $($engine.ExitCode)." }
    New-Item -ItemType File -Path $done | Out-Null
} catch {
    Set-Content -LiteralPath (Join-Path $ControlDir "$token.failed") -Value "$_"
    throw
}
