targetScope = 'subscription'

@minLength(1)
@maxLength(64)
@description('Name of the environment (e.g., dev, staging, prod)')
param environmentName string

@minLength(1)
@description('Primary location for all resources')
param location string

@description('Container image tag (defaults to latest)')
param imageTag string = 'latest'

var abbrs = {
  resourceGroup: 'rg-'
  containerRegistry: 'cr'
  containerAppsEnv: 'cae-'
  containerApp: 'ca-'
  apiManagement: 'apim-'
  logAnalytics: 'log-'
}

var resourceToken = toLower(uniqueString(subscription().id, environmentName, location))
var tags = {
  'azd-env-name': environmentName
}

// Resource Group
resource rg 'Microsoft.Resources/resourceGroups@2022-09-01' = {
  name: '${abbrs.resourceGroup}${environmentName}'
  location: location
  tags: tags
}

// Container Registry
module containerRegistry 'modules/container-registry.bicep' = {
  name: 'container-registry'
  scope: rg
  params: {
    name: '${abbrs.containerRegistry}${resourceToken}'
    location: location
    tags: tags
  }
}

// Container Apps Environment (includes Log Analytics)
module containerAppsEnv 'modules/container-apps-env.bicep' = {
  name: 'container-apps-env'
  scope: rg
  params: {
    name: '${abbrs.containerAppsEnv}${environmentName}'
    logAnalyticsName: '${abbrs.logAnalytics}${environmentName}'
    location: location
    tags: tags
  }
}

// MCP Server Container App
module containerApp 'modules/container-app.bicep' = {
  name: 'container-app'
  scope: rg
  params: {
    name: '${abbrs.containerApp}mcp-server-${environmentName}'
    location: location
    tags: tags
    containerAppsEnvironmentId: containerAppsEnv.outputs.environmentId
    containerRegistryLoginServer: containerRegistry.outputs.loginServer
    containerRegistryName: containerRegistry.outputs.name
    imageTag: imageTag
  }
}

// API Management
module apim 'modules/apim.bicep' = {
  name: 'apim'
  scope: rg
  params: {
    name: '${abbrs.apiManagement}${environmentName}'
    location: location
    tags: tags
    backendUrl: 'https://${containerApp.outputs.fqdn}'
  }
}

// Outputs for azd
output AZURE_CONTAINER_REGISTRY_ENDPOINT string = containerRegistry.outputs.loginServer
output AZURE_CONTAINER_REGISTRY_NAME string = containerRegistry.outputs.name
output AZURE_CONTAINER_APPS_ENVIRONMENT_ID string = containerAppsEnv.outputs.environmentId
output MCP_SERVER_FQDN string = containerApp.outputs.fqdn
output MCP_SERVER_URL string = 'https://${containerApp.outputs.fqdn}/mcp'
output APIM_GATEWAY_URL string = apim.outputs.gatewayUrl
output APIM_MCP_ENDPOINT string = '${apim.outputs.gatewayUrl}/mcp'
