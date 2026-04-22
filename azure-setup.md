# Deploying JarvisBot to Azure

This document outlines how to deploy the JarvisBot application to Azure.

For running background services like Discord bots, **Azure Container Instances (ACI)** is highly recommended.

## Azure Container Instances (ACI) vs Azure Kubernetes Service (AKS)
* **Azure Container Instances (ACI)** is a serverless container solution. It is ideal for this project because it runs a single container without needing to manage underlying virtual machines or complex orchestrations. It is also significantly cheaper for single long-running applications.
* **Azure Kubernetes Service (AKS)** is an enterprise-level orchestration platform. While powerful, it introduces unnecessary cost, complexity, and maintenance overhead for a single Discord bot container.

Because the bot needs to persist data (like VIP users and banned users) even when the container is stopped or restarted, we must map an **Azure File Share** to a directory inside the container (`/app/data`).

---

## 1. Automated Script Deployment (Recommended)

To quickly set up all the necessary Azure infrastructure, we have provided an automated bash script (`scripts/azure-deploy.sh`). This script handles the creation of the Resource Group, Azure Container Registry (ACR), Storage Account, File Share, and Azure Container Instance (ACI).

### Prerequisites:
- You must have the [Azure CLI](https://learn.microsoft.com/en-us/cli/azure/install-azure-cli) installed and configured on your machine.
- Docker must be installed locally.

### Steps:
1. Log in to Azure using the CLI:
   ```bash
   az login
   ```
2. Make the script executable:
   ```bash
   chmod +x scripts/azure-deploy.sh
   ```
3. Run the script and follow the prompts:
   ```bash
   ./scripts/azure-deploy.sh
   ```
4. During execution, the script will ask for:
   - Your preferred resource prefix (e.g., `jarvis`).
   - Your Discord Bot Token (`DISCORD_TOKEN`).
   - Your Gemini API Key (`GEMINI_API_KEY`, optional).
   - The Owner ID of the bot (`OWNER`, optional).

The script will automatically build your Docker container, push it to your private ACR, set up an Azure File Share for persistent storage, and launch the bot in ACI.

---

## 2. Manual Deployment via Azure Portal

If you prefer to set up the infrastructure manually, follow these steps:

### A. Create an Azure Container Registry (ACR)
1. Go to the Azure Portal and search for **Container Registries**.
2. Click **Create** and fill in the details (Resource Group, Registry Name, Pricing Tier: Basic is fine).
3. Once created, go to **Access Keys** in the Registry settings and enable **Admin user**.
4. Log into your registry locally and push the Docker image:
   ```bash
   az acr login --name <YourRegistryName>
   docker build -t <YourRegistryName>.azurecr.io/jarvisbot:latest .
   docker push <YourRegistryName>.azurecr.io/jarvisbot:latest
   ```

### B. Create an Azure Storage Account and File Share (For Persistence)
1. In the Azure Portal, search for **Storage Accounts** and click **Create**.
2. Once created, go to **File shares** under the "Data storage" menu.
3. Click **+ File share** and create one named `jarvisdata` (Transaction optimized tier is fine).
4. Go to **Access keys** on the Storage Account and copy `key1`. You will need this later.

### C. Deploy to Azure Container Instances (ACI)
1. In the Azure Portal, search for **Container Instances** and click **Create**.
2. **Basics Tab:**
   - Image source: Choose **Azure Container Registry**.
   - Select your ACR and the `jarvisbot` image you pushed.
3. **Advanced Tab:**
   - Under **Environment variables**, add:
     - `DISCORD_TOKEN` = (Your token)
     - `USE_AI_INTENT` = True
     - `GEMINI_API_KEY` = (Your token, if using AI intent)
     - `OWNER` = (Your Discord ID)
   - Under **Volume mounting**, click **+ Add new volume**:
     - Name: `datavolume`
     - Mount path: `/app/data`
     - Storage account name: (Name of the storage account created in step B)
     - Storage account key: (The `key1` copied in step B)
     - File share: `jarvisdata`
4. Review and Create the instance. Your bot will now be running continuously in the cloud.

---

## 3. GitHub Actions CI/CD Deployment

To automate deployments every time you push to the `main` branch, a GitHub Actions workflow has been provided in `.github/workflows/azure-deploy.yml`.

### Setup Instructions:
To enable this workflow, you need to add the following **Repository Secrets** to your GitHub repository (Settings -> Secrets and variables -> Actions):

- `AZURE_CREDENTIALS`: The output of the service principal creation (see below).
- `ACR_NAME`: The name of your Azure Container Registry.
- `ACI_NAME`: The name of the Azure Container Instance you want to update or create.
- `RESOURCE_GROUP`: The resource group containing your ACR and ACI.
- `STORAGE_ACCOUNT_NAME`: The name of your Azure Storage Account.
- `STORAGE_ACCOUNT_KEY`: The access key (`key1`) for your storage account.
- `DISCORD_TOKEN`: Your bot's Discord token.

### Generating `AZURE_CREDENTIALS`:
Run the following command in the Azure CLI to create a service principal with access to your resource group:

```bash
az ad sp create-for-rbac \
  --name "jarvis-github-actions" \
  --role contributor \
  --scopes /subscriptions/<Your-Subscription-ID>/resourceGroups/<Your-Resource-Group> \
  --sdk-auth
```

Copy the entire JSON output from that command and save it as the value for the `AZURE_CREDENTIALS` secret in GitHub.

Once configured, pushing code to the `main` branch will automatically build a new Docker image, push it to Azure, and restart the Container Instance.
