# Prepara e inicia o DrenaAssist em http://127.0.0.1:8001
# Uso: duplo clique em iniciar.bat, ou no PowerShell: .\iniciar.ps1
param(
    [int]$Porta = 8001,
    [switch]$SemTreinado
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

# 3. Modelo treinado (precisa de GPU NVIDIA). Sem GPU, a central funciona sem ele.
$servidorTreinado = $null
$jaLigado = $false
try { Invoke-WebRequest 'http://127.0.0.1:8766/api/tags' -UseBasicParsing -TimeoutSec 2 | Out-Null; $jaLigado = $true } catch { }
if ($jaLigado) {
    Passo 'Modelo treinado já está ligado em http://127.0.0.1:8766'
} elseif ($SemTreinado) {
    Passo 'Modelo treinado desligado por opção (-SemTreinado)'
} elseif (-not (Get-Command nvidia-smi -ErrorAction SilentlyContinue)) {
    Passo 'Nenhuma GPU NVIDIA encontrada: a central usa o Agente; o Agente treinado fica desligado'
} else {
    $pyT = Join-Path $PSScriptRoot '.venv-treinado\Scripts\python.exe'
    if (-not (Test-Path '.venv-treinado\.instalado')) {
        Passo 'GPU NVIDIA encontrada: preparando o modelo treinado (só na primeira vez; cerca de 2,5 GB de bibliotecas)'
        if (-not (Test-Path $pyT)) { & $python[0] @($python[1..9] | Where-Object { $_ }) -m venv .venv-treinado }
        & $pyT -m pip install --upgrade pip --quiet
        & $pyT -m pip install torch==2.8.0 --index-url https://download.pytorch.org/whl/cu128
        & $pyT -m pip install -r treino\requirements.txt
        if ($LASTEXITCODE -eq 0) { New-Item -ItemType File '.venv-treinado\.instalado' | Out-Null }
        else { Write-Host 'Não foi possível instalar o modelo treinado; a central segue sem ele.' -ForegroundColor Yellow }
    }
    if (Test-Path '.venv-treinado\.instalado') {
        Passo 'Ligando o modelo treinado em segundo plano (na primeira vez baixa o Qwen2.5-3B, cerca de 6 GB)'
        $log = Join-Path $PSScriptRoot '.venv-treinado\servidor.log'
        $servidorTreinado = Start-Process $pyT -ArgumentList '-m', 'treino.servidor_treinado' -WorkingDirectory $PSScriptRoot `
            -WindowStyle Hidden -RedirectStandardOutput $log -RedirectStandardError "$log.err" -PassThru
        Write-Host 'A central libera o Agente treinado sozinha quando ele ficar pronto. Registro em .venv-treinado\servidor.log'
    }
}

# 4. Fonte DrenaData opcional: usa a pasta vizinha se existir
foreach ($pasta in @('..\drenahub-bigdata\mvp\dados', '..\drenaData\mvp\dados')) {
    if (Test-Path $pasta) { $env:DRENA_V2_DATA_EXPORT_DIR = (Resolve-Path $pasta).Path; break }
}

# 5. API e navegador
Passo "Iniciando o DrenaAssist em http://127.0.0.1:$Porta (feche a janela ou Ctrl+C para parar)"
Start-Job -ScriptBlock { param($p) Start-Sleep -Seconds 6; Start-Process "http://127.0.0.1:$p/" } -ArgumentList $Porta | Out-Null
try {
    & $py -m uvicorn app.api:app --host 127.0.0.1 --port $Porta
} finally {
    if ($servidorTreinado -and -not $servidorTreinado.HasExited) { Stop-Process -Id $servidorTreinado.Id -Force }
}
