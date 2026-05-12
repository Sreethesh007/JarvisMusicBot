param(
    [string]$SubscriptionId = "<YOUR_SUBSCRIPTION_ID>",
    [string]$AcrName = "jarvisbotacr",
    [string]$ResourceGroup = "jarvis-bot",
    [string]$StorageAccountName = "jarvisbotsa",
    [string]$ContainerName = "jarvis-bot-container",
    [string]$FileShareName = "jarvis-bot-data",
    [string]$ImageName = "jarvis-bot",
    [string]$Location = "centralindia"
)

Set-StrictMode -Version Latest
$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Resolve-Path (Join-Path $scriptRoot "..")
$envFile = Join-Path $repoRoot ".env"
if (-not (Test-Path $envFile)) {
    Write-Error ".env file not found at $envFile. Create it before running this script."
    exit 1
}

$env = @{}
Get-Content $envFile | ForEach-Object {
    $line = $_.Trim()
    if (-not $line -or $line.StartsWith("#")) { return }
    $parts = $line -split "=", 2
    if ($parts.Count -ne 2) { return }
    $key = $parts[0].Trim()
    $value = $parts[1].Trim().Trim("'\"")
    $env[$key] = $value
}

$required = @("DISCORD_TOKEN", "OWNER", "USE_AI_INTENT")
foreach ($key in $required) {
    if (-not $env.ContainsKey($key) -or [string]::IsNullOrWhiteSpace($env[$key])) {
        Write-Error "Missing required env var '$key' in .env."
        exit 1
    }
}

$optionalKeys = @("GEMINI_API_KEY", "SPOTIFY_CLIENT_ID", "SPOTIFY_CLIENT_SECRET", "SPOTIFY_CLIENT_REFRESH_TOKEN", "AZURE_SUBSCRIPTION_ID", "SUBSCRIPTION_ID")
$envArgs = @(
    "DISCORD_TOKEN=$($env['DISCORD_TOKEN'])",
    "USE_AI_INTENT=$($env['USE_AI_INTENT'])",
    "OWNER=$($env['OWNER'])"
)
foreach ($key in $optionalKeys) {
    if ($env.ContainsKey($key) -and -not [string]::IsNullOrWhiteSpace($env[$key])) {
        $envArgs += "$key=$($env[$key])"
    }
}

Write-Host "Logging in to Azure..."
az login | Out-Null

$subscriptionFromEnv = $null
if ($env.ContainsKey('AZURE_SUBSCRIPTION_ID')) {
    $subscriptionFromEnv = $env['AZURE_SUBSCRIPTION_ID']
} elseif ($env.ContainsKey('SUBSCRIPTION_ID')) {
    $subscriptionFromEnv = $env['SUBSCRIPTION_ID']
}

$selectedSubscription = $null
if ($SubscriptionId -and $SubscriptionId -ne "<YOUR_SUBSCRIPTION_ID>") {
    $selectedSubscription = $SubscriptionId
} elseif ($subscriptionFromEnv) {
    $selectedSubscription = $subscriptionFromEnv
}

if ($selectedSubscription) {
    Write-Host "Setting Azure subscription to $selectedSubscription..."
    az account set --subscription $selectedSubscription | Out-Null
}

Write-Host "Logging in to ACR..."
az acr login --name $AcrName | Out-Null
$registry = "$AcrName.azurecr.io"
$imageTag = "$registry/$ImageName:latest"

Write-Host "Building Docker image..."
docker build -t "$ImageName:latest" "$repoRoot"

Write-Host "Tagging image..."
docker tag "$ImageName:latest" "$imageTag"

Write-Host "Pushing image to ACR..."
docker push "$imageTag"

Write-Host "Retrieving storage account key..."
$storageAccountKey = az storage account keys list --resource-group $ResourceGroup --account-name $StorageAccountName --query "[0].value" -o tsv

$cookieFile = Join-Path $repoRoot "cookies.txt"
if (Test-Path $cookieFile) {
    Write-Host "Uploading cookies.txt to Azure File Share..."
    $shareExists = az storage share exists --name $FileShareName --account-name $StorageAccountName --account-key $storageAccountKey --query exists -o tsv
    if ($shareExists -ne 'true') {
        Write-Error "Azure File Share '$FileShareName' does not exist. Create it before running this script."
        exit 1
    }
    az storage file upload --account-name $StorageAccountName --account-key $storageAccountKey --share-name $FileShareName --source $cookieFile --path "cookies.txt" --only-show-errors | Out-Null
}

Write-Host "Removing existing container if it exists..."
try {
    az container delete --name $ContainerName --resource-group $ResourceGroup --yes | Out-Null
    Start-Sleep -Seconds 5
} catch {
    Write-Warning "Container did not exist or deletion failed; continuing."
}

Write-Host "Creating container instance..."
az container create `
  --resource-group $ResourceGroup `
  --name $ContainerName `
  --image $imageTag `
  --cpu 1 `
  --memory 1 `
  --os-type Linux `
  --registry-login-server $registry `
  --registry-username (az acr credential show --name $AcrName --query username -o tsv) `
  --registry-password (az acr credential show --name $AcrName --query "passwords[0].value" -o tsv) `
  --azure-file-volume-account-name $StorageAccountName `
  --azure-file-volume-account-key $storageAccountKey `
  --azure-file-volume-share-name $FileShareName `
  --azure-file-volume-mount-path /app/data `
  --environment-variables $envArgs

Write-Host "Deployment complete. Container is using image $imageTag."