#!/bin/bash

# Exit on error
set -e

# Configuration Variables
RESOURCE_GROUP="jarvis-bot-rg"
LOCATION="eastus" # You can change this to a region closer to you
ACR_NAME="jarvisbotacr${RANDOM}" # ACR name must be globally unique
STORAGE_ACCOUNT_NAME="jarvisbotsa${RANDOM}" # Storage account name must be globally unique
FILE_SHARE_NAME="jarvis-bot-data"

echo "======================================================"
echo "Starting Azure Infrastructure Deployment"
echo "======================================================"

# 1. Create Resource Group
echo "Checking if Resource Group '$RESOURCE_GROUP' exists..."
if [ $(az group exists --name $RESOURCE_GROUP) = false ]; then
  echo "Creating Resource Group..."
  az group create --name $RESOURCE_GROUP --location $LOCATION
else
  echo "Resource Group '$RESOURCE_GROUP' already exists."
fi

# 2. Create Azure Container Registry (ACR)
echo "Checking if ACR exists in Resource Group..."
# Try to list ACRs in the resource group. If none, create one.
EXISTING_ACR=$(az acr list --resource-group $RESOURCE_GROUP --query "[0].name" -o tsv)

if [ -z "$EXISTING_ACR" ]; then
  echo "Creating Azure Container Registry (Basic tier)..."
  az acr create --resource-group $RESOURCE_GROUP --name $ACR_NAME --sku Basic --admin-enabled true
  echo "ACR '$ACR_NAME' created."
else
  ACR_NAME=$EXISTING_ACR
  echo "ACR '$ACR_NAME' already exists."
fi

# Get ACR Login Server
ACR_LOGIN_SERVER=$(az acr show --name $ACR_NAME --query loginServer -o tsv)
echo "ACR Login Server: $ACR_LOGIN_SERVER"

# 3. Create Storage Account
echo "Checking if Storage Account exists in Resource Group..."
EXISTING_SA=$(az storage account list --resource-group $RESOURCE_GROUP --query "[0].name" -o tsv)

if [ -z "$EXISTING_SA" ]; then
  echo "Creating Storage Account (Standard_LRS)..."
  az storage account create \
    --resource-group $RESOURCE_GROUP \
    --name $STORAGE_ACCOUNT_NAME \
    --location $LOCATION \
    --sku Standard_LRS \
    --kind StorageV2 \
    --allow-blob-public-access false
  echo "Storage Account '$STORAGE_ACCOUNT_NAME' created."
else
  STORAGE_ACCOUNT_NAME=$EXISTING_SA
  echo "Storage Account '$STORAGE_ACCOUNT_NAME' already exists."
fi

# Get Storage Account Key
STORAGE_ACCOUNT_KEY=$(az storage account keys list \
  --resource-group $RESOURCE_GROUP \
  --account-name $STORAGE_ACCOUNT_NAME \
  --query "[0].value" -o tsv)

# 4. Create File Share
echo "Checking if File Share '$FILE_SHARE_NAME' exists..."
SHARE_EXISTS=$(az storage share exists \
  --name $FILE_SHARE_NAME \
  --account-name $STORAGE_ACCOUNT_NAME \
  --account-key "$STORAGE_ACCOUNT_KEY" \
  --query exists -o tsv)

if [ "$SHARE_EXISTS" = "false" ]; then
  echo "Creating File Share..."
  az storage share create \
    --name $FILE_SHARE_NAME \
    --account-name $STORAGE_ACCOUNT_NAME \
    --account-key "$STORAGE_ACCOUNT_KEY" \
    --quota 5 # Setting a small 5GB quota to avoid accidental large usage
  echo "File Share '$FILE_SHARE_NAME' created."
else
  echo "File Share '$FILE_SHARE_NAME' already exists."
fi

echo "======================================================"
echo "Infrastructure Deployment Complete."
echo "======================================================"

# Output variables needed for GitHub Actions
echo "ACR_NAME=$ACR_NAME"
echo "ACR_LOGIN_SERVER=$ACR_LOGIN_SERVER"
echo "STORAGE_ACCOUNT_NAME=$STORAGE_ACCOUNT_NAME"
# Note: We don't print the Storage Account Key to stdout for security.
# The GitHub Action will extract it directly.
