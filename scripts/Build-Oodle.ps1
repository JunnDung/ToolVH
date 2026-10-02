param([string]$CargoExecutable = 'cargo')
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$taskTarget = Join-Path $taskRoot 'build\oodle'
& $CargoExecutable build --locked --release --target wasm32-unknown-unknown --manifest-path (Join-Path $taskRoot 'native\oodle\Cargo.toml') --target-dir $taskTarget
if ($LASTEXITCODE -ne 0) { throw 'Oodle WASM build failed. Install Rust and rustup target add wasm32-unknown-unknown first.' }
$taskArtifact = Join-Path $taskTarget 'wasm32-unknown-unknown\release\toolvh_oodle.wasm'
Copy-Item -LiteralPath $taskArtifact -Destination (Join-Path $taskRoot 'toolvh\data\toolvh_oodle.wasm') -Force
Write-Output 'Oodle WASM rebuilt from pinned Cargo.lock; run tests before packaging.'
