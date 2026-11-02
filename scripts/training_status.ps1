$ErrorActionPreference = 'Stop'
$projectPath = Split-Path -Parent $PSScriptRoot
$runRoot = Join-Path $projectPath 'artifacts/runs'
if (-not (Test-Path -LiteralPath $runRoot)) {
    Write-Output 'No GPU training runs have been created yet.'
    exit 0
}
Get-ChildItem -LiteralPath $runRoot -Filter status.json -Recurse | ForEach-Object {
    $trainingState = Get-Content -LiteralPath $_.FullName -Raw | ConvertFrom-Json
    $trainingProcess = Get-Process -Id $trainingState.pid -ErrorAction SilentlyContinue
    [pscustomobject]@{
        Run = $_.Directory.Name
        State = $trainingState.state
        ProcessAlive = [bool]$trainingProcess
        Epoch = "$($trainingState.epoch)/$($trainingState.epochs)"
        Stage = $trainingState.stage
        Batch = "$($trainingState.batch)/$($trainingState.batches)"
        Loss = $trainingState.loss
        File = $_.FullName
    }
} | Format-List
