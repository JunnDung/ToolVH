param([string]$OutputDirectory = 'dist\0.6.0')
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
& '.\.venv\Scripts\python.exe' -m PyInstaller --noconfirm --distpath $OutputDirectory packaging/ToolVH.spec
if ($LASTEXITCODE -ne 0) { throw 'Build failed' }
Write-Output "Ready: $OutputDirectory\ToolVH\ToolVH.exe (keep the whole ToolVH folder)"
