#!/bin/bash

# Exit on error
set -e

echo "======================================================"
echo "  JarvisBot Azure Deployment Script"
echo "======================================================"
echo ""

# Ensure Azure CLI is logged in
if ! az account show > /dev/null 2>&1; then
    echo "You are not logged into Azure CLI. Please run 'az login' first."
    exit 1
fi

# Variables
read -p "Enter a unique prefix for your Azure resources (e.g., jarvisbotxyz): " PREFIX
PREFIX=${PREFIX,,} # convert to lowercase
LOCATION="eastus"  # Default location, can be changed

RG_NAME="${PREFIX}-rg"
ACR_NAME="${PREFIX}acr"
STORAGE_ACCOUNT="${PREFIX}storage"
FILE_SHARE="jarvisdata"
ACI_NAME="${PREFIX}-container"
IMAGE_NAME="${ACR_NAME}.azurecr.io/jarvisbot:latest"

# Get environment variables
read -p "Enter your Discord Bot Token: " DISCORD_TOKEN
read -p "Enter your Gemini API Key (leave blank if none): " GEMINI_API_KEY
read -p "Enter your Discord Owner ID (leave blank if none): " OWNER_ID

echo ""
echo "Starting deployment to Resource Group: $RG_NAME..."

# 1. Create Resource Group
echo "--> Creating Resource Group..."
az group create --name $RG_NAME --location $LOCATION > /dev/null

# 2. Create Azure Container Registry (ACR)
echo "--> Creating Azure Container Registry..."
az acr create --resource-group $RG_NAME --name $ACR_NAME --sku Basic --admin-enabled true > /dev/null

# Get ACR Credentials
ACR_USERNAME=$(az acr credential show --name $ACR_NAME --query "username" -o tsv)
ACR_PASSWORD=$(az acr credential show --name $ACR_NAME --query "passwords[0].value" -o tsv)

# 3. Build and Push Docker Image
echo "--> Logging into ACR and building Docker image..."
az acr login --name $ACR_NAME
docker build -t $IMAGE_NAME .
echo "--> Pushing Docker image to ACR..."
docker push $IMAGE_NAME

# 4. Create Storage Account & File Share
echo "--> Creating Storage Account for persistent data..."
az storage account create \
  --resource-group $RG_NAME \
  --name $STORAGE_ACCOUNT \
  --location $LOCATION \
  --sku Standard_LRS > /dev/null

echo "--> Getting Storage Account Key..."
STORAGE_KEY=$(az storage account keys list --resource-group $RG_NAME --account-name $STORAGE_ACCOUNT --query "[0].value" -o tsv)

echo "--> Creating File Share..."
az storage share create \
  --name $FILE_SHARE \
  --account-name $STORAGE_ACCOUNT \
  --account-key $STORAGE_KEY > /dev/null

# 5. Deploy Azure Container Instance (ACI)
echo "--> Deploying Azure Container Instance..."

# Prepare environment variables string safely
ENV_VARS="DISCORD_TOKEN=$DISCORD_TOKEN USE_AI_INTENT=True"
if [ ! -z "$GEMINI_API_KEY" ]; then
    ENV_VARS="$ENV_VARS GEMINI_API_KEY=$GEMINI_API_KEY"
fi
if [ ! -z "$OWNER_ID" ]; then
    ENV_VARS="$ENV_VARS OWNER=$OWNER_ID"
fi

az container create \
  --resource-group $RG_NAME \
  --name $ACI_NAME \
  --image $IMAGE_NAME \
  --registry-login-server "${ACR_NAME}.azurecr.io" \
  --registry-username $ACR_USERNAME \
  --registry-password $ACR_PASSWORD \
  --dns-name-label $ACI_NAME \
  --ports 80 \
  --azure-file-volume-account-name $STORAGE_ACCOUNT \
  --azure-file-volume-account-key $STORAGE_KEY \
  --azure-file-volume-share-name $FILE_SHARE \
  --azure-file-volume-mount-path "/app/data" \
  --environment-variables $ENV_VARS > /dev/null

echo "======================================================"
echo "Deployment Complete!"
echo "Your bot should be online shortly."
echo "Check the status in the Azure Portal or using the CLI:"
echo "az container logs --resource-group $RG_NAME --name $ACI_NAME"
echo "======================================================"
