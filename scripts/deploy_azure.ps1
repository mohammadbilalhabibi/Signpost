<#
.SYNOPSIS
  Deploy Signpost to Azure Container Apps (Consumption plan, scale to zero).

.DESCRIPTION
  Run from the project folder after `az login`:
    powershell -ExecutionPolicy Bypass -File scripts\deploy_azure.ps1             # first deploy or update
    powershell -ExecutionPolicy Bypass -File scripts\deploy_azure.ps1 -SkipBudget # without the budget step

  The image is built and pushed by GitHub Actions (.github/workflows/docker.yml) to
  ghcr.io/mohammadbilalhabibi/signpost; the package must be public so Azure can pull it
  without credentials.

  Steps:
    1. Show the subscription that will be used.
    2. Register the resource providers Container Apps needs (once per subscription).
    3. Create the resource group in the allowed region.
    4. Create the Container Apps environment (Consumption only, no Log Analytics workspace).
    5. Create or update the app from deploy\containerapp.yaml (image, size, env vars,
       probes, scale 0..1, external HTTPS ingress on port 7860).
    6. Set the LLM_API_KEY secret from .env (the value is never printed).
    7. Replace the running replica so it uses the secret.
    8. Print the public URL.
    9. Create a monthly budget with e-mail alerts (skip with -SkipBudget).
#>
param(
    [string]$Location = "francecentral",
    [string]$ResourceGroup = "signpost-rg",
    [string]$Environment = "signpost-env",
    [string]$AppName = "signpost",
    [string]$Image = "ghcr.io/mohammadbilalhabibi/signpost:latest",
    # Measured: docker stats on a Linux runner 1.60 GiB after startup, peak 2.07 GiB after 3
    # questions (LLM unreachable); Azure WorkingSetBytes peak 2.44 GiB while answering 3 real
    # questions. 1.75 vCPU / 3.5 GiB is the smallest Consumption size with >= 25 % headroom.
    [string]$Cpu = "1.75",
    [string]$Memory = "3.5Gi",
    [string]$LlmProvider = "openai",
    [string]$LlmBaseUrl = "https://api.openai.com/v1",
    [string]$LlmModel = "gpt-6-luna",
    [int]$DailyQuestionLimit = 200,
    [int]$BudgetUsd = 20,
    [switch]$SkipBudget
)

$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$az = (Get-Command az -ErrorAction SilentlyContinue).Source
if (-not $az) { $az = "C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin\az.cmd" }

function Invoke-Az {
    $out = & $az @args
    if ($LASTEXITCODE -ne 0) { throw "az $($args[0..2] -join ' ') ... failed (exit code $LASTEXITCODE)" }
    return $out
}

function Find-Az {
    # Existence checks: "not found" is an expected answer here, not an error.
    $previous = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try { $out = & $az @args 2>$null } finally { $ErrorActionPreference = $previous }
    if ($LASTEXITCODE -ne 0) { return $null }
    return $out
}

# 1. Which subscription? (az login must have been run)
Write-Host "[1/9] Subscription:" -ForegroundColor Cyan
$sub = Invoke-Az account show --query "{name:name, id:id, user:user.name}" -o json | ConvertFrom-Json
Write-Host "      $($sub.name) ($($sub.id))"

# 2. Resource providers (no cost; takes a minute the first time)
Write-Host "[2/9] Registering resource providers..." -ForegroundColor Cyan
foreach ($provider in @("Microsoft.App", "Microsoft.OperationalInsights")) {
    Invoke-Az provider register --namespace $provider --wait | Out-Null
    Write-Host "      $provider registered"
}

# 3. Resource group (your subscription only allows francecentral, norwayeast, polandcentral,
#    belgiumcentral and switzerlandnorth)
Write-Host "[3/9] Resource group $ResourceGroup in $Location..." -ForegroundColor Cyan
Invoke-Az group create --name $ResourceGroup --location $Location -o none

# 4. Environment: Consumption only (pay per use, free monthly grant), no Log Analytics
#    workspace (avoids log ingestion costs; `az containerapp logs show` still streams logs)
Write-Host "[4/9] Container Apps environment $Environment..." -ForegroundColor Cyan
$envId = Find-Az containerapp env show -n $Environment -g $ResourceGroup --query id -o tsv
if (-not $envId) {
    Invoke-Az containerapp env create --name $Environment --resource-group $ResourceGroup `
        --location $Location --logs-destination none -o none
    $envId = Invoke-Az containerapp env show -n $Environment -g $ResourceGroup --query id -o tsv
}
Write-Host "      $envId"

# 5. App from the YAML template (placeholders filled in; no secret value in the file)
Write-Host "[5/9] Creating/updating the app $AppName ($Cpu vCPU, $Memory)..." -ForegroundColor Cyan
$yaml = Get-Content (Join-Path $root "deploy\containerapp.yaml") -Raw
$values = @{
    "__LOCATION__" = $Location; "__ENVIRONMENT_ID__" = $envId; "__IMAGE__" = $Image
    "__CPU__" = $Cpu; "__MEMORY__" = $Memory; "__LLM_PROVIDER__" = $LlmProvider
    "__LLM_BASE_URL__" = $LlmBaseUrl; "__LLM_MODEL__" = $LlmModel
    "__DAILY_QUESTION_LIMIT__" = "$DailyQuestionLimit"
}
foreach ($key in $values.Keys) { $yaml = $yaml.Replace($key, $values[$key]) }
$tmp = Join-Path $env:TEMP "signpost-containerapp.yaml"
[System.IO.File]::WriteAllText($tmp, $yaml)
try {
    $exists = Find-Az containerapp show -n $AppName -g $ResourceGroup --query name -o tsv
    if ($exists) {
        Invoke-Az containerapp update --name $AppName --resource-group $ResourceGroup --yaml $tmp -o none
    } else {
        Invoke-Az containerapp create --name $AppName --resource-group $ResourceGroup --yaml $tmp -o none
    }
} finally {
    Remove-Item $tmp -ErrorAction SilentlyContinue
}

# 6. Secret from .env (never echoed)
Write-Host "[6/9] Setting the LLM_API_KEY secret from .env..." -ForegroundColor Cyan
$line = Get-Content (Join-Path $root ".env") | Where-Object { $_ -match '^\s*LLM_API_KEY\s*=' } | Select-Object -First 1
$key = if ($line) { ($line -split '=', 2)[1].Trim().Trim('"').Trim("'") } else { "" }
if (-not $key) { throw "LLM_API_KEY is missing in .env" }
Invoke-Az containerapp secret set --name $AppName --resource-group $ResourceGroup --secrets "llm-api-key=$key" -o none
Remove-Variable key, line

# 7. Replace the running replica so it reads the current secret. "revision restart" and
#    revision suffixes are not supported in express environments (which `az containerapp
#    env create` now creates), but changing an environment variable replaces the replica.
Write-Host "[7/9] Restarting the replica (DEPLOYED_AT env var)..." -ForegroundColor Cyan
$stamp = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
Invoke-Az containerapp update --name $AppName --resource-group $ResourceGroup --set-env-vars "DEPLOYED_AT=$stamp" -o none

# 8. Public URL
$fqdn = Invoke-Az containerapp show -n $AppName -g $ResourceGroup --query properties.configuration.ingress.fqdn -o tsv
Write-Host "[8/9] App URL: https://$fqdn  (the first request after idle wakes the app)" -ForegroundColor Green

# 9. Budget with e-mail alerts at 50 %, 80 % (actual) and 100 % (forecast)
if ($SkipBudget) {
    Write-Host "[9/9] Budget skipped." -ForegroundColor DarkGray
} else {
    Write-Host "[9/9] Budget of $BudgetUsd USD/month with alerts to $($sub.user)..." -ForegroundColor Cyan
    $start = (Get-Date -Day 1).ToString("yyyy-MM-01T00:00:00Z")
    $end = (Get-Date -Day 1).AddYears(1).ToString("yyyy-MM-01T00:00:00Z")
    $alert = { param($t, $kind) @{ enabled = $true; operator = "GreaterThan"; threshold = $t; thresholdType = $kind; contactEmails = @($sub.user) } }
    $body = @{
        properties = @{
            category = "Cost"; amount = $BudgetUsd; timeGrain = "Monthly"
            timePeriod = @{ startDate = $start; endDate = $end }
            notifications = @{
                actual50 = (& $alert 50 "Actual"); actual80 = (& $alert 80 "Actual")
                forecast100 = (& $alert 100 "Forecasted")
            }
        }
    } | ConvertTo-Json -Depth 6
    $bodyFile = Join-Path $env:TEMP "signpost-budget.json"
    [System.IO.File]::WriteAllText($bodyFile, $body)
    $url = "https://management.azure.com/subscriptions/$($sub.id)/providers/Microsoft.Consumption/budgets/signpost-monthly-$($BudgetUsd)usd?api-version=2023-05-01"
    & $az rest --method put --url $url --body "@$bodyFile" -o none
    if ($LASTEXITCODE -eq 0) { Write-Host "      budget created" -ForegroundColor Green }
    else { Write-Host "      Azure rejected the budget; create it in the portal (see README)." -ForegroundColor Yellow }
    Remove-Item $bodyFile -ErrorAction SilentlyContinue
}
