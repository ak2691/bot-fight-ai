param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('contracts', 'validate', 'validate-batch', 'simulate', 'simulate-batch')]
    [string]$Mode,

    [string]$BotFightServerRoot = 'C:\dev\botfight\server',

    [Parameter(ValueFromPipeline = $true)]
    [string]$InputJson
)

$ErrorActionPreference = 'Stop'
$toolRoot = $PSScriptRoot
$buildRoot = Join-Path $toolRoot '.build'
$classesRoot = Join-Path $buildRoot 'classes'
$classpathFile = Join-Path $buildRoot 'classpath.txt'
$bridgeSource = Join-Path $toolRoot 'BotFightBridge.java'
$mavenWrapper = Join-Path $BotFightServerRoot 'mvnw.cmd'
$serverClasses = Join-Path $BotFightServerRoot 'target\classes'
$sourceRepositoryRoot = (& git -C $BotFightServerRoot rev-parse --show-toplevel).Trim()
$sourceRevision = (& git -C $BotFightServerRoot rev-parse HEAD).Trim()
$sourceDirty = [bool](& git -C $sourceRepositoryRoot status --porcelain --untracked-files=no -- `
    'server/src/main/java/com/example/botfight/simulation' `
    'server/src/main/java/com/example/botfight/service/submission/BotSubmissionValidationService.java' `
    'server/src/main/java/com/example/botfight/DTO/match')

New-Item -ItemType Directory -Force -Path $classesRoot | Out-Null

& $mavenWrapper -q -f (Join-Path $BotFightServerRoot 'pom.xml') compile
if ($LASTEXITCODE -ne 0) { throw 'Bot Fight server compilation failed.' }

& $mavenWrapper -q -f (Join-Path $BotFightServerRoot 'pom.xml') dependency:build-classpath "-Dmdep.outputFile=$classpathFile" "-Dmdep.includeScope=runtime"
if ($LASTEXITCODE -ne 0) { throw 'Could not build the Bot Fight runtime classpath.' }

$dependencyClasspath = (Get-Content -Raw -LiteralPath $classpathFile).Trim()
$runtimeClasspath = "$serverClasses;$dependencyClasspath"

& javac -cp $runtimeClasspath -d $classesRoot $bridgeSource
if ($LASTEXITCODE -ne 0) { throw 'Bot Fight bridge compilation failed.' }

$bridgeClasspath = "$classesRoot;$runtimeClasspath"
if ($Mode -eq 'contracts') {
    & java "-Dbotfight.source.revision=$sourceRevision" "-Dbotfight.source.dirty=$($sourceDirty.ToString().ToLowerInvariant())" -cp $bridgeClasspath BotFightBridge $Mode
} else {
    if ([string]::IsNullOrWhiteSpace($InputJson)) {
        $InputJson = [Console]::In.ReadToEnd()
    }
    $InputJson | & java -cp $bridgeClasspath BotFightBridge $Mode
}
if ($LASTEXITCODE -ne 0) { throw "Bot Fight bridge operation '$Mode' failed." }
