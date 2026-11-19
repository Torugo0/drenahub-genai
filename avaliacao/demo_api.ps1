param(
    [string]$BaseUrl = 'http://127.0.0.1:8001'
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$runStamp = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssfffZ')
$runDir = Join-Path $repoRoot "avaliacao/resultados/demo_api/$runStamp"
New-Item -ItemType Directory -Path $runDir -Force | Out-Null
$utf8NoBom = [System.Text.UTF8Encoding]::new($false)
$apiBase = $BaseUrl.TrimEnd('/')

$toolLog = if ($env:DRENA_TOOL_LOG_PATH) {
    $env:DRENA_TOOL_LOG_PATH
} else {
    Join-Path $repoRoot 'avaliacao/tool_calls.jsonl'
}
$toolRowsBefore = if (Test-Path -LiteralPath $toolLog) {
    @(Get-Content -LiteralPath $toolLog).Count
} else {
    0
}

function Invoke-RecordedRequest {
    param(
        [string]$Name,
        [string]$Url,
        [string]$Method,
        [hashtable]$Payload
    )
    $startedUtc = (Get-Date).ToUniversalTime().ToString('o')
    $timer = [System.Diagnostics.Stopwatch]::StartNew()
    $rawBody = ''
    $statusCode = $null
    $failure = $null
    try {
        if ($Method -eq 'GET') {
            $reply = Invoke-WebRequest -Uri $Url -Method Get -UseBasicParsing -TimeoutSec 300
        } else {
            $requestJson = $Payload | ConvertTo-Json -Depth 12 -Compress
            $bytes = [System.Text.Encoding]::UTF8.GetBytes($requestJson)
            $reply = Invoke-WebRequest -Uri $Url -Method Post -ContentType 'application/json; charset=utf-8' -Body $bytes -UseBasicParsing -TimeoutSec 300
        }
        $statusCode = [int]$reply.StatusCode
        if ($reply.RawContentStream -and $reply.RawContentStream -is [System.IO.MemoryStream]) {
            $rawBody = [System.Text.Encoding]::UTF8.GetString($reply.RawContentStream.ToArray())
        } else {
            $rawBody = [string]$reply.Content
        }
    } catch {
        $failure = $_.Exception.Message
        if ($_.Exception.Response) {
            $statusCode = [int]$_.Exception.Response.StatusCode
            $stream = $_.Exception.Response.GetResponseStream()
            if ($stream) {
                $reader = [System.IO.StreamReader]::new($stream, [System.Text.Encoding]::UTF8)
                try { $rawBody = $reader.ReadToEnd() } finally { $reader.Dispose() }
            }
        }
        if (-not $rawBody) {
            $rawBody = @{ error = $failure; http_status = $statusCode } | ConvertTo-Json -Compress
        }
    } finally {
        $timer.Stop()
    }
    $fileName = "$Name.json"
    $target = Join-Path $runDir $fileName
    [System.IO.File]::WriteAllText($target, $rawBody, $utf8NoBom)
    return [pscustomobject]@{
        name = $Name
        timestamp_utc = $startedUtc
        method = $Method
        url = $Url
        request = $Payload
        http_status = $statusCode
        elapsed_ms = [math]::Round($timer.Elapsed.TotalMilliseconds, 2)
        response_file = $fileName
        error = $failure
    }
}

$records = @()
$records += Invoke-RecordedRequest -Name '00_health' -Url "$apiBase/health" -Method 'GET' -Payload @{}
$records += Invoke-RecordedRequest -Name '01_rag_documento' -Url "$apiBase/assistant/ask" -Method 'POST' -Payload @{
    question = 'O que deve constar no registro de inspeção de drenagem?'
    configuration = 'rag'
}
$records += Invoke-RecordedRequest -Name '02_rag_recusa' -Url "$apiBase/assistant/ask" -Method 'POST' -Payload @{
    question = 'Qual foi a última leitura do sensor do RALO-01?'
    configuration = 'rag'
}
$records += Invoke-RecordedRequest -Name '03_agent_prioridade' -Url "$apiBase/assistant/ask" -Method 'POST' -Payload @{
    question = 'Por que a garagem A está com prioridade alta?'
    configuration = 'agent'
    location_id = 'GAR-A'
}
$records += Invoke-RecordedRequest -Name '04_agent_pre_chamado' -Url "$apiBase/assistant/ask" -Method 'POST' -Payload @{
    question = 'Prepare um rascunho de ordem de serviço para a ocorrência OC-001.'
    configuration = 'agent'
    point_id = 'RALO-01'
}

if (Test-Path -LiteralPath $toolLog) {
    $newToolRows = @(Get-Content -LiteralPath $toolLog | Select-Object -Skip $toolRowsBefore)
    if ($newToolRows.Count -gt 0) {
        [System.IO.File]::WriteAllText(
            (Join-Path $runDir 'tool_calls.jsonl'),
            (($newToolRows -join [Environment]::NewLine) + [Environment]::NewLine),
            $utf8NoBom
        )
    }
}

$manifest = @{
    generated_utc = (Get-Date).ToUniversalTime().ToString('o')
    base_url = $apiBase
    run_directory = "avaliacao/resultados/demo_api/$runStamp"
    records = $records
    note = 'Respostas HTTP reais da API local. Registros operacionais sintéticos. Nenhum arquivo do benchmark foi substituído.'
} | ConvertTo-Json -Depth 20
[System.IO.File]::WriteAllText((Join-Path $runDir 'manifesto.json'), $manifest, $utf8NoBom)

$records | Format-Table name, http_status, elapsed_ms, response_file -AutoSize
Write-Output "Evidências salvas em $runDir"
