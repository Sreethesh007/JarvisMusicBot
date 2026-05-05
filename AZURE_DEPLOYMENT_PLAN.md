# Azure Deployment Plan for Discord Bot

This document outlines the deployment strategy for the Discord bot to Azure, optimized to fit within a ₹4000 (~$48 USD) monthly budget. It leverages Azure Container Instances (ACI) for serverless container execution, Azure Container Registry (ACR) for image storage, and Azure Files for persistent data.

## Architecture Overview

*   **Azure Container Registry (ACR):** A Basic tier registry used to store the Docker images built by the GitHub Actions CI/CD pipeline.
*   **Azure Container Instances (ACI):** A lightweight, serverless compute service used to run the bot. It will pull the latest image from ACR and run continuously.
*   **Azure Storage Account (Azure Files):** Provides persistent storage for the bot's data (e.g., `data/` directory for banned users, VIP users, etc.). This ensures state is maintained across container restarts.
*   **GitHub Actions:** Handles the CI/CD pipeline. When code is pushed to the `main` branch, it builds the Docker image, pushes it to ACR, and updates the ACI instance.

## Cost Breakdown (Estimated)

The goal is to keep the monthly cost well under ₹4000 (~$48 USD).

1.  **Azure Container Instances (ACI) - Linux:**
    *   Configuration: 1 vCPU, 1 GB Memory.
    *   Assuming 730 hours (full month) of continuous running.
    *   *Estimated Cost:* ~$30 - $35 USD (~₹2500 - ₹2900).
2.  **Azure Container Registry (ACR) - Basic Tier:**
    *   Includes 10 GB of storage, which is more than enough for a few versions of the bot's image.
    *   *Estimated Cost:* ~$5 USD (~₹415).
3.  **Azure Storage (Azure Files) - Standard LRS:**
    *   Transaction Optimized or Hot tier, minimal storage (e.g., < 1 GB).
    *   *Estimated Cost:* ~$1 - $2 USD (~₹83 - ₹166).
4.  **Bandwidth / Data Transfer:**
    *   Inbound data is free. Outbound data (e.g., streaming audio) will incur minor costs, but the first 100 GB is usually free.
    *   *Estimated Cost:* ~$0 - $2 USD.

**Total Estimated Monthly Cost:** ~$36 - $44 USD (~₹3000 - ₹3650), safely within the ₹4000 budget limit.

## Prerequisites and Initial Setup

### 1. Azure Setup

You will need to create a Service Principal in Azure so that GitHub Actions can authenticate and deploy resources.

1.  Log in to Azure CLI or Azure Cloud Shell:
    ```bash
    az login
    ```
2.  Create a Service Principal with Contributor access to your subscription:
    ```bash
    az ad sp create-for-rbac --name "github-actions-deploy" --role contributor --scopes /subscriptions/<YOUR_SUBSCRIPTION_ID> --sdk-auth
    ```
    *Replace `<YOUR_SUBSCRIPTION_ID>` with your actual Azure subscription ID.*
3.  Copy the entire JSON output from the command above. You will need this for the `AZURE_CREDENTIALS` GitHub Secret.

### 2. GitHub Secrets Configuration

To securely manage credentials, you must add the following secrets to your GitHub repository (Go to Settings -> Secrets and variables -> Actions -> New repository secret):

*   **`AZURE_CREDENTIALS`**: Paste the entire JSON output obtained from the Service Principal creation step above.
*   **`DISCORD_TOKEN`**: Your Discord bot token.
*   *Optional:* **`GEMINI_API_KEY`**: Your Google Gemini API key if you are using AI intents (`USE_AI_INTENT=True`).
*   *Optional:* **`SPOTIFY_CLIENT_ID`** & **`SPOTIFY_CLIENT_SECRET`**: If you require Spotify integration.

## Deployment Automation

The deployment is fully automated using GitHub Actions and a bash script.

### 1. Infrastructure Script (`scripts/azure-deploy.sh`)

This script handles the creation of the necessary Azure resources: Resource Group, Storage Account, File Share, and Container Registry. It is designed to be idempotent (it won't fail if resources already exist).

### 2. CI/CD Pipeline (`.github/workflows/azure-deploy.yml`)

The GitHub Actions workflow is triggered on pushes to the `main` branch. It performs the following steps:

1.  **Checkout Code:** Pulls the latest code from the repository.
2.  **Azure Login:** Authenticates with Azure using the `AZURE_CREDENTIALS` secret.
3.  **Infrastructure Setup:** Runs the `scripts/azure-deploy.sh` script to ensure all required resources exist and retrieves their keys.
4.  **Build & Push Docker Image:** Logs into ACR, builds the Docker image from the provided `Dockerfile`, and pushes it to the registry.
5.  **Deploy to ACI:** Deploys the container to Azure Container Instances. It mounts the Azure File Share to the `/app/data` directory for persistent storage and injects the Discord bot token and other secrets as environment variables securely.

## Ongoing Management

### Updates and Scaling

*   **Code Updates:** To update the bot, simply push your changes to the `main` branch in GitHub. The GitHub Actions pipeline will automatically build a new image and restart the container with the latest code.
*   **Scaling:** If the bot needs more resources (e.g., if it starts handling multiple busy voice channels simultaneously), you can modify the CPU and memory limits in the `.github/workflows/azure-deploy.yml` file under the `az container create` command. Note that increasing resources will increase the monthly cost.

### Monitoring

*   **Logs:** You can view the real-time logs of the running container using the Azure CLI or the Azure Portal.
    ```bash
    az container logs --resource-group jarvis-bot-rg --name jarvis-bot-container
    ```
*   **Metrics:** Monitor CPU, memory, and network usage in the Azure Portal under the Container Instances resource to ensure it stays within limits and doesn't throttle.

### Data Management

The bot's state (banned users, VIP users, etc.) is saved in JSON files located in the `data/` directory. Because this directory is mounted to an Azure File Share, the data will persist even if the container crashes, restarts, or is redeployed. You can browse and edit these files directly through the Azure Portal (Storage accounts -> File shares).
