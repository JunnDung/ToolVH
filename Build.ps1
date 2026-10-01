param(
    [string]$OutputDirectory = '',
    [string]$PythonExecutable = '',
    [switch]$NoArchive
)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not $PythonExecutable) { $PythonExecutable = Join-Path $PSScriptRoot '.venv\Scripts\python.exe' }
if (-not (Test-Path -LiteralPath $PythonExecutable)) {
    throw 'Missing Python environment. Create .venv and install requirements-build.txt first (see README.md).'
}
$versionSource = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'toolvh\__init__.py') -Raw
$versionMatch = [regex]::Match($versionSource, '__version__\s*=\s*"([0-9]+\.[0-9]+\.[0-9]+)"')
if (-not $versionMatch.Success) { throw 'Cannot read ToolVH version' }
$version = $versionMatch.Groups[1].Value
if (-not $OutputDirectory) { $OutputDirectory = Join-Path 'dist' $version }
& $PythonExecutable -m PyInstaller --noconfirm --distpath $OutputDirectory packaging/ToolVH.spec
if ($LASTEXITCODE -ne 0) { throw 'Build failed' }
$packageDirectory = Join-Path $OutputDirectory 'ToolVH'
foreach ($document in @('LICENSE', 'README.md', 'THIRD_PARTY.md')) {
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot $document) -Destination $packageDirectory -Force
}
# Include the dependency licenses shipped by the installed wheels.
$sitePackages = & $PythonExecutable -c "import sysconfig; print(sysconfig.get_path('purelib'))"
if ($LASTEXITCODE -ne 0) { throw 'Cannot locate dependency licenses' }
$licenseRoot = Join-Path $packageDirectory 'THIRD-PARTY-LICENSES'
foreach ($metadata in Get-ChildItem -LiteralPath $sitePackages -Directory -Filter '*.dist-info') {
    $licenseFolder = Join-Path $metadata.FullName 'licenses'
    $licenseFiles = @(Get-ChildItem -LiteralPath $metadata.FullName -File | Where-Object { $_.Name -match '^(LICENSE|COPYING|NOTICE)' })
    if ((Test-Path -LiteralPath $licenseFolder) -or $licenseFiles.Count) {
        $destination = Join-Path $licenseRoot $metadata.Name
        New-Item -ItemType Directory -Path $destination -Force | Out-Null
        if (Test-Path -LiteralPath $licenseFolder) { Copy-Item -LiteralPath $licenseFolder -Destination $destination -Recurse -Force }
        foreach ($licenseFile in $licenseFiles) { Copy-Item -LiteralPath $licenseFile.FullName -Destination $destination -Force }
    }
}
Write-Output "Ready: $packageDirectory\ToolVH.exe (keep the whole ToolVH folder)"
if (-not $NoArchive) {
    $archive = Join-Path $OutputDirectory "ToolVH-$version-windows-x64.zip"
    Compress-Archive -LiteralPath $packageDirectory -DestinationPath $archive -Force
    $checksum = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant()
    "$checksum  $([IO.Path]::GetFileName($archive))" | Set-Content -LiteralPath "$archive.sha256" -Encoding ascii
    Write-Output "GitHub Release assets: $archive and $archive.sha256"
}
