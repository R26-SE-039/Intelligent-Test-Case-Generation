<#
    azure-deploy.ps1 — deploy Component 2 (Intelligent Test Case Generation)
    FastAPI backend to Azure App Service for Containers.

    Prereqs:
      - Azure CLI installed:  winget install Microsoft.AzureCLI
      - Logged in:            az login
      - Docker NOT required   (image is built in the cloud via `az acr build`)

    Fill in the CONFIG block below (Neon URL + LLM key), then run:
      pwsh ./deploy/azure-deploy.ps1
    or in Windows PowerShell:
      powershell -File .\deploy\azure-deploy.ps1
#>

$ErrorActionPreference = 'Stop'

# ─────────────────────────────────────────────────────────────
# CONFIG — edit these
# ─────────────────────────────────────────────────────────────
$Subscription = 'Azure for Students'

# Names. ACR + WebApp names must be GLOBALLY UNIQUE and lowercase alphanumeric.
# If creation fails as "already taken", change them.
$ResourceGroup = 'nextgenqa-rg'
$Location      = 'southeastasia'        # close to Neon ap-southeast-1
$AcrName       = 'nextgenqac2dasun'     # ACR name: a-z0-9 only, 5-50 chars
$PlanName      = 'nextgenqa-plan'
$AppName       = 'nextgenqa-c2-dasun'   # -> https://<AppName>.azurewebsites.net
$ImageTag      = 'c2-backend:latest'

# SKU: 'B1' (1.75GB, ~$13/mo, ~7 months on $100) is enough now that the unused
# spaCy/torch model was removed. Use 'B2' (3.5GB, ~$26/mo) for extra headroom.
$Sku = 'B1'

# Secrets / runtime env (mirror your backend/.env)
$DatabaseUrl     = 'postgresql://neondb_owner:PASSWORD@ep-xxx.ap-southeast-1.aws.neon.tech/nextgen_qa?sslmode=require'
$LlmProvider     = 'anthropic'
$LlmModel        = 'claude-sonnet-4-6'
$LlmApiKey       = 'sk-ant-REPLACE_ME'
$AgentVisionModel= 'claude-sonnet-4-6'
# Optional GitHub execution feature — leave blank if unused:
$GithubToken     = ''
$GithubRepo      = ''

$BudgetAmount = 90   # alert threshold (of your $100 credit)

# ─────────────────────────────────────────────────────────────
# Derived
# ─────────────────────────────────────────────────────────────
$BackendPath = Join-Path $PSScriptRoot '..\backend'
$LoginServer = "$AcrName.azurecr.io"
$Image       = "$LoginServer/$ImageTag"

Write-Host "==> Using subscription: $Subscription" -ForegroundColor Cyan
az account set --subscription $Subscription

# 1. Resource group
Write-Host "==> Resource group: $ResourceGroup ($Location)" -ForegroundColor Cyan
az group create -n $ResourceGroup -l $Location | Out-Null

# 2. Container registry (admin creds enabled so the web app can pull)
Write-Host "==> Container registry: $AcrName" -ForegroundColor Cyan
az acr create -n $AcrName -g $ResourceGroup --sku Basic --admin-enabled true | Out-Null

# 3. Build the image in the cloud from ./backend/Dockerfile
Write-Host "==> Building image remotely (this takes a few minutes)..." -ForegroundColor Cyan
az acr build -r $AcrName -t $ImageTag $BackendPath

# 4. App Service plan (Linux)
Write-Host "==> App Service plan: $PlanName ($Sku)" -ForegroundColor Cyan
az appservice plan create -n $PlanName -g $ResourceGroup --is-linux --sku $Sku | Out-Null

# 5. Web app from the container image
Write-Host "==> Web app: $AppName" -ForegroundColor Cyan
az webapp create -n $AppName -g $ResourceGroup -p $PlanName `
    --deployment-container-image-name $Image | Out-Null

# Wire ACR pull credentials to the web app
$acrCreds = az acr credential show -n $AcrName | ConvertFrom-Json
$acrUser  = $acrCreds.username
$acrPass  = $acrCreds.passwords[0].value
az webapp config container set -n $AppName -g $ResourceGroup `
    --docker-custom-image-name $Image `
    --docker-registry-server-url "https://$LoginServer" `
    --docker-registry-server-user $acrUser `
    --docker-registry-server-password $acrPass | Out-Null

# 6. Port + platform settings (container listens on 8002)
Write-Host "==> Applying app settings" -ForegroundColor Cyan
az webapp config appsettings set -n $AppName -g $ResourceGroup --settings `
    WEBSITES_PORT=8002 `
    SCM_DO_BUILD_DURING_DEPLOYMENT=false `
    DATABASE_URL="$DatabaseUrl" `
    LLM_PROVIDER="$LlmProvider" `
    LLM_MODEL="$LlmModel" `
    LLM_API_KEY="$LlmApiKey" `
    AGENT_VISION_MODEL="$AgentVisionModel" `
    GITHUB_TOKEN="$GithubToken" `
    GITHUB_REPO="$GithubRepo" | Out-Null

# 7. Enable WebSockets (OFF by default on Azure — needed for agent/crawler streams)
az webapp config set -n $AppName -g $ResourceGroup --web-sockets-enabled true | Out-Null

# 8. Budget alert guardrail
Write-Host "==> Creating budget alert at `$$BudgetAmount" -ForegroundColor Cyan
try {
    az consumption budget create --budget-name c2-budget `
        --amount $BudgetAmount --time-grain Monthly --category Cost `
        --resource-group $ResourceGroup | Out-Null
} catch {
    Write-Warning "Budget alert not created via CLI — set one in portal: Cost Management > Budgets"
}

# Restart to pick everything up
az webapp restart -n $AppName -g $ResourceGroup | Out-Null

Write-Host ""
Write-Host "Deployed. URL:  https://$AppName.azurewebsites.net" -ForegroundColor Green
Write-Host "Health check:   https://$AppName.azurewebsites.net/health" -ForegroundColor Green
Write-Host "Live logs:      az webapp log tail -n $AppName -g $ResourceGroup" -ForegroundColor Green
Write-Host ""
Write-Host "Frontend/gateway: point /api/test-case at the URL above and use wss:// (not ws://)." -ForegroundColor Yellow
