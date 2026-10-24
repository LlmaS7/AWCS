param([switch]$PrepareOnly)
$ErrorActionPreference = 'Stop'
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
$env:PYTHONUTF8 = '1'
$projectPath = 'E:\_PROJECTS\AWCS'
$targetPath = [System.IO.Path]::GetFullPath((Join-Path $projectPath '.temp\agent_testing_v6'))
$expectedParent = [System.IO.Path]::GetFullPath((Join-Path $projectPath '.temp'))
if ([System.IO.Path]::GetDirectoryName($targetPath) -ne $expectedParent) { throw 'Unexpected test destination' }
foreach ($checkPath in @($projectPath, $expectedParent)) {
    $item = Get-Item -LiteralPath $checkPath
    if ($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) { throw "Reparse point is not accepted: $checkPath" }
}
$markerPath = Join-Path $targetPath 'suite_owner.json'
if (Test-Path -LiteralPath $targetPath) {
    if ((Get-Item -LiteralPath $targetPath).Attributes -band [System.IO.FileAttributes]::ReparsePoint) { throw 'Destination is a reparse point' }
    if (!(Test-Path -LiteralPath $markerPath)) { throw 'Destination already exists without suite ownership marker' }
    $owner = Get-Content -LiteralPath $markerPath -Raw | ConvertFrom-Json
    if ($owner.version -ne 'v6' -or $owner.path -ne $targetPath) { throw 'Destination ownership mismatch' }
} else {
    New-Item -ItemType Directory -Path $targetPath | Out-Null
    @{version='v6';path=$targetPath} | ConvertTo-Json | Set-Content -LiteralPath $markerPath -Encoding utf8
}
$fileNames = @('harness.py','oracle.py','fixtures.py','cases.py','checks.py','matrix.py','challenges.py','e2e.py','run_agent_suite.py','validate_driver.py','review_existing.py','continue_run.py','regression_v6.py','run_local.ps1','Start_Agent_Test.ps1','README.md')
foreach ($fileName in $fileNames) {
    $sourcePath = Join-Path $PSScriptRoot $fileName
    $destinationPath = Join-Path $targetPath $fileName
    if (Test-Path -LiteralPath $destinationPath) {
        if ((Get-FileHash -LiteralPath $sourcePath -Algorithm SHA256).Hash -ne (Get-FileHash -LiteralPath $destinationPath -Algorithm SHA256).Hash) { throw "Different existing script: $fileName; preserve its run and use a new suite version" }
    } else { Copy-Item -LiteralPath $sourcePath -Destination $destinationPath }
}
$pythonPath = Join-Path $projectPath '.venv\Scripts\python.exe'
$suiteArgs = @('-B', (Join-Path $targetPath 'continue_run.py'))
if ($PrepareOnly) { $suiteArgs += '--prepare-only' }
Write-Output "TEST_ROOT=$targetPath"
& $pythonPath @suiteArgs
exit $LASTEXITCODE
