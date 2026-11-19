<#
.SYNOPSIS
  Deploy Signpost to a Hugging Face Docker Space (Windows PowerShell 5.1 or 7).

.DESCRIPTION
  Run from the project folder:
    powershell -ExecutionPolicy Bypass -File scripts\deploy_space.ps1 -UploadReranker   # first time
    powershell -ExecutionPolicy Bypass -File scripts\deploy_space.ps1                   # later deploys
    powershell -ExecutionPolicy Bypass -File scripts\deploy_space.ps1 -DryRun           # only list files

  Steps:
    1. Check that the hf CLI is logged in (hf auth login, with a WRITE token).
    2. Only with -UploadReranker: create the public model repo and upload the int8 ONNX
       reranker from models\ plus its model card (one time, ~570 MB).
    3. Create the Docker Space if it does not exist yet.
    4. Copy only the files the image needs into a temporary staging folder.
    5. Upload the staging folder to the Space (this starts a new build).
    6. Set the non-secret Space variables.
    7. Remind you to set the LLM_API_KEY secret in the Space settings (never done here).
    8. Show how to watch the build log.
#>
param(
    [string]$HfUser = "MohammadBilalHabibi12345",
    [string]$SpaceName = "signpost",
    [string]$ModelRepoName = "signpost-reranker-onnx-int8",
    [string]$LlmProvider = "openai",
    [string]$LlmBaseUrl = "https://api.openai.com/v1",
    [string]$LlmModel = "gpt-6-luna",
    [int]$DailyQuestionLimit = 200,
    [switch]$UploadReranker,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$hf = Join-Path $root ".venv\Scripts\hf.exe"
if (-not (Test-Path $hf)) { $hf = "hf" }
$spaceId = "$HfUser/$SpaceName"
$modelId = "$HfUser/$ModelRepoName"

function Invoke-Hf {
    & $hf @args
    if ($LASTEXITCODE -ne 0) { throw "hf $($args -join ' ') failed (exit code $LASTEXITCODE)" }
}

# 1. Logged in? (prints your username; the token itself is never shown)
Write-Host "[1/8] Checking Hugging Face login..." -ForegroundColor Cyan
if ($DryRun) { Write-Host "      (dry run: no login check, no uploads)" }
else { & $hf auth whoami }
if (-not $DryRun -and $LASTEXITCODE -ne 0) {
    throw "Not logged in. Create a WRITE token at https://huggingface.co/settings/tokens and run: .venv\Scripts\hf.exe auth login"
}

# 2. One time: the reranker model repo the Dockerfile downloads from.
if ($UploadReranker -and -not $DryRun) {
    Write-Host "[2/8] Uploading the ONNX reranker to $modelId ..." -ForegroundColor Cyan
    $modelDir = Join-Path $root "models\bge-reranker-v2-m3-onnx-int8"
    if (-not (Test-Path (Join-Path $modelDir "model.onnx"))) {
        throw "No model at $modelDir. Run: python scripts\export_reranker.py"
    }
    Invoke-Hf repos create $modelId --type model --public --exist-ok
    Invoke-Hf upload $modelId $modelDir . --repo-type model --commit-message "Upload int8 ONNX reranker"
    Invoke-Hf upload $modelId (Join-Path $root "deploy\RERANKER_MODEL_CARD.md") README.md --repo-type model --commit-message "Add model card"
} else {
    Write-Host "[2/8] Skipping reranker upload (use -UploadReranker the first time)." -ForegroundColor DarkGray
}

# 3. The Space (Docker SDK, free CPU hardware by default).
Write-Host "[3/8] Creating the Space $spaceId if needed..." -ForegroundColor Cyan
if (-not $DryRun) { Invoke-Hf repos create $spaceId --type space --sdk docker --public --exist-ok }

# 4. Staging folder with exactly what the Dockerfile copies (no PDFs, no secrets, no models).
Write-Host "[4/8] Preparing files..." -ForegroundColor Cyan
$staging = Join-Path $env:TEMP "signpost-space-staging"
if (Test-Path $staging) { Remove-Item $staging -Recurse -Force }
New-Item -ItemType Directory -Path $staging | Out-Null
foreach ($file in @("Dockerfile", ".dockerignore", "pyproject.toml", "constraints.txt")) {
    Copy-Item (Join-Path $root $file) $staging
}
Copy-Item (Join-Path $root "deploy\SPACE_README.md") (Join-Path $staging "README.md")
Copy-Item (Join-Path $root "app") $staging -Recurse
Copy-Item (Join-Path $root "scripts") $staging -Recurse
$collection = "DIT_Arrival_RAG_English\DIT_Arrival_RAG_English"
$target = Join-Path $staging $collection
New-Item -ItemType Directory -Path $target -Force | Out-Null
Copy-Item (Join-Path $root "$collection\sources.json") $target
Copy-Item (Join-Path $root "$collection\text") $target -Recurse
Get-ChildItem $staging -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force
$count = (Get-ChildItem $staging -Recurse -File).Count
Write-Host "      $count files in $staging"
if ($DryRun) {
    Get-ChildItem $staging -Recurse -File | ForEach-Object { $_.FullName.Substring($staging.Length + 1) }
    Write-Host "Dry run finished; nothing was uploaded." -ForegroundColor Green
    return
}

# 5. Upload (one commit); stale files in app/, scripts/ and the collection are removed.
Write-Host "[5/8] Uploading to the Space (this starts a build)..." -ForegroundColor Cyan
Invoke-Hf upload $spaceId $staging . --repo-type space --commit-message "Deploy Signpost" `
    --delete "app/**" --delete "scripts/**" --delete "DIT_Arrival_RAG_English/**"

# 6. Non-secret settings as Space variables (your tested model differs from the code default).
Write-Host "[6/8] Setting Space variables..." -ForegroundColor Cyan
Invoke-Hf spaces variables add $spaceId `
    -e "LLM_PROVIDER=$LlmProvider" `
    -e "LLM_BASE_URL=$LlmBaseUrl" `
    -e "LLM_MODEL=$LlmModel" `
    -e "TRUST_FORWARDED_FOR=true" `
    -e "DAILY_QUESTION_LIMIT=$DailyQuestionLimit"

# 7. The API key is a secret: set it yourself in the browser.
Write-Host "[7/8] Set the secret LLM_API_KEY (once) at:" -ForegroundColor Yellow
Write-Host "      https://huggingface.co/spaces/$spaceId/settings  ->  Variables and secrets  ->  New secret"

# 8. Watch the build.
Write-Host "[8/8] Done. Watch the build with:" -ForegroundColor Green
Write-Host "      .venv\Scripts\hf.exe spaces logs $spaceId --build -f"
Write-Host "      App: https://huggingface.co/spaces/$spaceId"
