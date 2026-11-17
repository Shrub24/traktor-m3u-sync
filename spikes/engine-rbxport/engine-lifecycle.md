# Engine DJ lifecycle pilot

Use a scratch Engine library with Auto Analysis enabled and at least one known unanalyzed track already inserted. Close Engine before starting. The task runs under the signed-in Windows user; it does not install a boot trigger or shut down the VM.

From **Windows PowerShell** as the DJ user, in the directory where you copied the script:

```powershell
.\engine-lifecycle.ps1 -Install -EngineExe 'C:\path\to\Engine DJ.exe'
Start-ScheduledTask -TaskName 'Engine DJ analysis pilot'
```

Use the shortcut's actual executable target. Keep the script at the same path after registering it. If Windows marks the copied script as downloaded, inspect it before using `Unblock-File -LiteralPath .\engine-lifecycle.ps1`.

Run this on the Linux host if the scratch DB is on a shared mount. Replace the path and track ID. Run it before launching Engine, again when analysis looks finished but the pilot dialog is still waiting, and once more after **OK** and Engine's exit. This reads the DB directly; do not copy an open database file to make the observation. If SQLite reports a lock, record that rather than treating it as evidence that nothing was committed.

```sh
sqlite3 -readonly -header -column '/path/to/scratch/m.db' '
  SELECT t.id, t.isAnalyzed, length(p.beatData) AS beat_bytes
  FROM Track t LEFT JOIN PerformanceData p ON p.trackId = t.id
  WHERE t.id IN (123);'
```

Check the task result and timestamped log:

```powershell
Get-ScheduledTaskInfo -TaskName 'Engine DJ analysis pilot'
Get-Content (Join-Path $env:LOCALAPPDATA 'EngineDJ-analysis-pilot.log')
```

A successful task proves the launched process accepted a normal close and exited with code zero, not that analysis completed. The trial passes when the selected rows were pending before launch, have a saved grid after exit, and the task succeeds without an Engine dialog blocking close. If rows are only committed at exit, a separate completion signal (such as a verified Engine UI indicator) is needed for hands-off close.

Remove the pilot when done:

```powershell
Unregister-ScheduledTask -TaskName 'Engine DJ analysis pilot' -Confirm:$false
```
