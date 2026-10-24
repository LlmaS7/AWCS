param([switch]$PrepareOnly)
$ErrorActionPreference = 'Stop'
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
$env:PYTHONUTF8 = '1'
$pythonPath = 'E:\_PROJECTS\AWCS\.venv\Scripts\python.exe'
$suiteArgs = @('-B', (Join-Path $PSScriptRoot 'continue_run.py'))
if ($PrepareOnly) { $suiteArgs += '--prepare-only' }
& $pythonPath @suiteArgs
exit $LASTEXITCODE
