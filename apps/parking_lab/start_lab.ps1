Push-Location (Resolve-Path (Join-Path $PSScriptRoot '..\..'))
try {
    python -m apps.parking_lab.workbench serve @args
} finally {
    Pop-Location
}
