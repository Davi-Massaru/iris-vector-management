param([string]$Script = '/workspace/tools/probe.py', [string]$Namespace = 'USER', [string]$Container = 'iris-vector-dev')
$ErrorActionPreference = 'Stop'
if ($Script -notmatch '^/[a-zA-Z0-9_./-]+$' -or $Namespace -notmatch '^[%a-zA-Z0-9_]+$') { throw 'Invalid script or namespace' }
$commands = "set runner=##class(%SYS.Python).Import(`"runpy`") do runner.`"run_path`"(`"$Script`") write !,`"VECTOR_SCRIPT_OK`",!`nhalt`n"
$result = $commands | docker --context default exec -i $Container iris session IRIS -U $Namespace
$result | Write-Output
if ($LASTEXITCODE -ne 0) { throw 'IRIS session failed' }
if (($result -join "`n") -notmatch '(?m)^VECTOR_SCRIPT_OK\s*$') { throw 'Embedded Python script failed' }
