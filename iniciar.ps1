# Prepara e inicia o DrenaAssist em http://127.0.0.1:8001
# Uso: duplo clique em iniciar.bat, ou no PowerShell: .\iniciar.ps1
param(
    [int]$Porta = 8001
)

$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$modelo = 'qwen2.5:3b-instruct'

function Passo($texto) { Write-Host "`n>> $texto" -ForegroundColor Cyan }

# 1. Python e ambiente virtual
Passo 'Verificando Python'
$python = $null
foreach ($candidato in @('py -3.10', 'py -3', 'python')) {
    $partes = $candidato.Split(' ')
    try {
        $versao = & $partes[0] @($partes[1..9] | Where-Object { $_ }) --version 2>$null
        if ($versao -match 'Python 3\.(1[0-9])') { $python = $partes; break }
    } catch { }
}
if (-not $python) {
    Write-Host 'Python 3.10 ou superior não encontrado. Instale em https://www.python.org/downloads/ e rode de novo.' -ForegroundColor Red
    exit 1
}

if (-not (Test-Path '.venv\Scripts\python.exe')) {
    Passo 'Criando ambiente virtual (.venv)'
    & $python[0] @($python[1..9] | Where-Object { $_ }) -m venv .venv
}
$py = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'

if (-not (Test-Path '.venv\.instalado')) {
    Passo 'Instalando dependências (só na primeira vez; pode levar alguns minutos)'
    & $py -m pip install --upgrade pip --quiet
    & $py -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { Write-Host 'Falha ao instalar dependências.' -ForegroundColor Red; exit 1 }
    New-Item -ItemType File '.venv\.instalado' | Out-Null
}

# 2. Ollama e modelo
Passo 'Verificando Ollama'
if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) {
    Write-Host 'Ollama não encontrado. Instale em https://ollama.com/download/windows, abra o Ollama e rode de novo.' -ForegroundColor Red
    exit 1
}
& ollama list *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Host 'Iniciando o serviço do Ollama...'
    Start-Process ollama -ArgumentList 'serve' -WindowStyle Hidden
    Start-Sleep -Seconds 4
}
if (-not ((& ollama list) -match [regex]::Escape($modelo))) {
    Passo "Baixando o modelo $modelo (cerca de 2 GB, só na primeira vez)"
    & ollama pull $modelo
}

# 3. Fonte DrenaData opcional: usa a pasta vizinha se existir
foreach ($pasta in @('..\drenahub-bigdata\mvp\dados', '..\drenaData\mvp\dados')) {
    if (Test-Path $pasta) { $env:DRENA_V2_DATA_EXPORT_DIR = (Resolve-Path $pasta).Path; break }
}

# 4. API e navegador
Passo "Iniciando o DrenaAssist em http://127.0.0.1:$Porta (Ctrl+C para parar)"
Start-Job -ScriptBlock { param($p) Start-Sleep -Seconds 6; Start-Process "http://127.0.0.1:$p/" } -ArgumentList $Porta | Out-Null
& $py -m uvicorn app.api:app --host 127.0.0.1 --port $Porta
