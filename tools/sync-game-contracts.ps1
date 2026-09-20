param(
    [string]$BotFightServerRoot = 'C:\dev\botfight\server'
)

$ErrorActionPreference = 'Stop'
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$outputDirectory = Join-Path $repositoryRoot 'ai-service\app\data'
$outputPath = Join-Path $outputDirectory 'duel-v1-game-knowledge.json'
$temporaryPath = Join-Path $outputDirectory 'duel-v1-game-knowledge.tmp.json'

New-Item -ItemType Directory -Force -Path $outputDirectory | Out-Null
& (Join-Path $PSScriptRoot 'invoke-botfight-bridge.ps1') `
    -Mode contracts `
    -BotFightServerRoot $BotFightServerRoot |
    Set-Content -Encoding utf8 -LiteralPath $temporaryPath

$parsed = Get-Content -Raw -LiteralPath $temporaryPath | ConvertFrom-Json
if ($parsed.rulesetVersion -ne 'duel-v1' -or $parsed.brainSchemaVersion -ne 'bot-logic-tree-v1') {
    throw 'Exported game contracts do not contain the expected version identifiers.'
}

Move-Item -Force -LiteralPath $temporaryPath -Destination $outputPath
Write-Output "Updated $outputPath"
