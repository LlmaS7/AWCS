[CmdletBinding()]
param([switch]$Apply)

$ErrorActionPreference = 'Stop'
$cleanupRoot = [System.IO.Path]::GetFullPath($PSScriptRoot)
$cleanupPrefix = $cleanupRoot.TrimEnd('\') + '\'
$projectRoot = Split-Path -Parent $cleanupRoot
if ((Split-Path -Leaf $cleanupRoot) -ne '.temp' -or (Split-Path -Leaf $projectRoot) -ne 'AWCS') {
    throw 'Run this script only from AWCS\.temp.'
}

# Exact allowlist: generated report previews, debug output and verified duplicates.
# No wildcard or recursive deletion. Test runs, fixtures, credentials and builders remain.
$cleanupRelativeFiles = @(
    'file_io_test_d7ff8e5a64f342d8ab203e98d1cb6fdc.md',
    'import_drop_preview.png',
    'report_cleanup\d07-1440.png',
    'report_cleanup\d07-390.png',
    'report_cleanup\d07-768.png',
    'report_cleanup\export.json',
    'report_rebuild\critical-modal.png',
    'report_rebuild\debug_presentation.cjs',
    'report_rebuild\debug_presentation_mouse.cjs',
    'report_rebuild\desktop-agent.png',
    'report_rebuild\desktop-critical.png',
    'report_rebuild\desktop-overview.png',
    'report_rebuild\downloaded-summary.json',
    'report_rebuild\downloads\430ae4cb-aa04-4986-a499-b09b19e8c43b',
    'report_rebuild\downloads\75184d82-39e9-4041-8bcb-c448986142e4',
    'report_rebuild\inline_script_0.js',
    'report_rebuild\inline_script_1.js',
    'report_rebuild\mobile-agent.png',
    'report_rebuild\mobile-overview.png',
    'report_rebuild\print-preview.pdf',
    'report_rebuild\print_final_page.png',
    'report_rebuild\print_page_1.png',
    'report_rebuild\print_page_11.png',
    'report_rebuild\print_page_22.png',
    'testing\output\playwright\AWCS_evidence_export.json',
    'testing\output\playwright\report-desktop-final.png',
    'testing\output\playwright\report-desktop.png',
    'testing\output\playwright\report-mobile-replay.png',
    'testing\output\playwright\report-mobile.png',
    'testing\output\playwright\report-print-check.pdf',
    'testing\output\playwright\report-replay-desktop-final.png',
    'testing\output\playwright\report-replay.png',
    'testing\output\playwright\report_qa_output.txt',
    'testing\交付测试结论.md',
    'testing\修复后测试结论.md',
    'testing\64台追加测试结论.md'
)

# Completed browser downloads and browser session snapshots are reproducible.
# Keep the builders, their input HTML/CSS/JS, QA summaries and saved test evidence.
foreach ($relativeDirectory in @('report_cleanup\downloads', 'report_rebuild\downloads', 'testing\.playwright-cli')) {
    $directoryPath = Join-Path $cleanupRoot $relativeDirectory
    if (Test-Path -LiteralPath $directoryPath -PathType Container) {
        $directoryEntry = Get-Item -LiteralPath $directoryPath -Force
        if ($directoryEntry.Attributes -band [System.IO.FileAttributes]::ReparsePoint) { throw 'Refusing reparse-point directory.' }
        foreach ($entry in Get-ChildItem -LiteralPath $directoryPath -File -Force) {
            $cleanupRelativeFiles += $entry.FullName.Substring($cleanupPrefix.Length)
        }
    }
}

# These three runs contain synthetic self-check output only. The canonical offline
# run, all real-provider runs (including interruptions), and their evidence remain.
foreach ($runName in @('20261022_142922_5bb2a6', '20261022_143025_e9d9b3', '20261022_143123_f1c3ff')) {
    $runPath = Join-Path $cleanupRoot ('d07_retest\runs\' + $runName)
    if (-not (Test-Path -LiteralPath $runPath -PathType Container)) { continue }
    $runEntry = Get-Item -LiteralPath $runPath -Force
    if ($runEntry.Attributes -band [System.IO.FileAttributes]::ReparsePoint) { throw 'Refusing reparse-point run.' }
    $summary = Get-Content -LiteralPath (Join-Path $runPath 'summary.json') -Encoding UTF8 -Raw | ConvertFrom-Json
    if ($summary.mode -ne 'OFFLINE_SYNTHETIC') { throw "Not a synthetic run: $runName" }
    if (@(Get-ChildItem -LiteralPath $runPath -Recurse -Force | Where-Object { $_.Attributes -band [System.IO.FileAttributes]::ReparsePoint }).Count) {
        throw "Reparse point inside run: $runName"
    }
    foreach ($entry in Get-ChildItem -LiteralPath $runPath -Recurse -File -Force) {
        $cleanupRelativeFiles += $entry.FullName.Substring($cleanupPrefix.Length)
    }
}
$cleanupRelativeFiles = @($cleanupRelativeFiles | Select-Object -Unique)

function Assert-CleanupPath([string]$CandidatePath) {
    $absolutePath = [System.IO.Path]::GetFullPath($CandidatePath)
    if (-not $absolutePath.StartsWith($cleanupPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Target outside AWCS\.temp: $absolutePath"
    }
    $entry = Get-Item -LiteralPath $absolutePath -Force
    $current = $entry
    while ($null -ne $current -and $current.FullName.StartsWith($cleanupRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
        if ($current.Attributes -band [System.IO.FileAttributes]::ReparsePoint) {
            throw "Reparse point in target path: $($current.FullName)"
        }
        if ($current -is [System.IO.DirectoryInfo]) { $current = $current.Parent } else { $current = $current.Directory }
    }
    return $entry
}

foreach ($reportName in @('交付测试结论.md', '修复后测试结论.md', '64台追加测试结论.md')) {
    $sourcePath = Join-Path $cleanupRoot ('testing\' + $reportName)
    if (-not (Test-Path -LiteralPath $sourcePath -PathType Leaf)) { continue }
    $archiveRoot = Join-Path $projectRoot '.report\test_res\archive\20261022_整合前'
    $sourceHash = (Get-FileHash -LiteralPath $sourcePath -Algorithm SHA256).Hash
    $archiveHashes = @(Get-ChildItem -LiteralPath $archiveRoot -File -Filter '*.md' | Get-FileHash -Algorithm SHA256 | ForEach-Object Hash)
    if ($sourceHash -notin $archiveHashes) {
        throw "Archived report differs; refusing deletion: $reportName"
    }
}

$targets = @()
foreach ($relativePath in $cleanupRelativeFiles) {
    $candidatePath = Join-Path $cleanupRoot $relativePath
    if (-not (Test-Path -LiteralPath $candidatePath)) { continue }
    $entry = Assert-CleanupPath $candidatePath
    if ($entry.PSIsContainer) { throw "Expected a file: $candidatePath" }
    $targets += $entry
}
$freedBytes = ($targets | Measure-Object -Property Length -Sum).Sum
if ($null -eq $freedBytes) { $freedBytes = 0 }

if (-not $Apply) {
    $targets | Select-Object FullName, Length | Format-Table -AutoSize
    [pscustomobject]@{ mode = 'PREVIEW'; files = $targets.Count; bytes = $freedBytes; MiB = [Math]::Round($freedBytes / 1MB, 2) } | ConvertTo-Json
    return
}

$deletionSet = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::OrdinalIgnoreCase)
foreach ($entry in $targets) { [void]$deletionSet.Add($entry.FullName) }
$retainedBefore = @{}
foreach ($entry in Get-ChildItem -LiteralPath $cleanupRoot -Recurse -Force -File) {
    if (-not $deletionSet.Contains($entry.FullName)) {
        $retainedBefore[$entry.FullName] = @($entry.Length, $entry.LastWriteTimeUtc.Ticks)
    }
}
$reportPath = Join-Path $projectRoot '.report\AWCS_测试报告.html'
$reportHashBefore = (Get-FileHash -LiteralPath $reportPath -Algorithm SHA256).Hash

foreach ($entry in $targets) {
    $verifiedEntry = Assert-CleanupPath $entry.FullName
    if ($verifiedEntry.Length -ne $entry.Length -or $verifiedEntry.LastWriteTimeUtc -ne $entry.LastWriteTimeUtc) {
        throw "Target changed after preflight: $($entry.FullName)"
    }
    Remove-Item -LiteralPath $entry.FullName -Force
}
$emptyCandidates = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::OrdinalIgnoreCase)
foreach ($entry in $targets) {
    $parentPath = Split-Path -Parent $entry.FullName
    while ($parentPath.StartsWith($cleanupPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        [void]$emptyCandidates.Add($parentPath)
        $parentPath = Split-Path -Parent $parentPath
    }
}
foreach ($directoryPath in @($emptyCandidates | Sort-Object Length -Descending)) {
    if (Test-Path -LiteralPath $directoryPath -PathType Container) {
        $null = Assert-CleanupPath $directoryPath
        if (@(Get-ChildItem -LiteralPath $directoryPath -Force).Count -eq 0) {
            Remove-Item -LiteralPath $directoryPath -Force
        }
    }
}

foreach ($retainedPath in $retainedBefore.Keys) {
    $entry = Get-Item -LiteralPath $retainedPath -Force
    $expected = $retainedBefore[$retainedPath]
    if ($entry.Length -ne $expected[0] -or $entry.LastWriteTimeUtc.Ticks -ne $expected[1]) {
        throw "Retained file changed: $retainedPath"
    }
}
foreach ($entry in $targets) {
    if (Test-Path -LiteralPath $entry.FullName) { throw "Deletion failed: $($entry.FullName)" }
}
if ((Get-FileHash -LiteralPath $reportPath -Algorithm SHA256).Hash -ne $reportHashBefore) {
    throw 'Final HTML report changed.'
}
$audit = [pscustomobject]@{
    status = 'PASS'
    cleaned_at = [DateTimeOffset]::Now.ToOffset([TimeSpan]::FromHours(8)).ToString('o')
    deleted_files = $targets.Count
    freed_bytes = $freedBytes
    freed_MiB = [Math]::Round($freedBytes / 1MB, 2)
    retained_files_verified_unchanged = $retainedBefore.Count
    final_html_unchanged = $true
    deleted_paths = @($targets | ForEach-Object { $_.FullName.Substring($cleanupPrefix.Length) })
}
$audit | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $cleanupRoot 'cleanup_audit.json') -Encoding UTF8
$audit | Select-Object status, deleted_files, freed_bytes, freed_MiB, retained_files_verified_unchanged, final_html_unchanged | ConvertTo-Json
