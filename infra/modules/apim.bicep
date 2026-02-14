@description('Name of the API Management instance')
param name string

@description('Location for the resource')
param location string

@description('Tags for the resource')
param tags object = {}

@description('Backend URL for the MCP Container App')
param backendUrl string

resource apim 'Microsoft.ApiManagement/service@2023-09-01-preview' = {
  name: name
  location: location
  tags: tags
  sku: {
    name: 'StandardV2'
    capacity: 1
  }
  properties: {
    publisherEmail: 'admin@contoso.com'
    publisherName: 'Databricks MCP Server'
  }
}

// Backend pointing to the Container App (used by the MCP server registration)
resource backend 'Microsoft.ApiManagement/service/backends@2023-09-01-preview' = {
  parent: apim
  name: 'mcp-server-backend'
  properties: {
    protocol: 'http'
    url: backendUrl
    tls: {
      validateCertificateChain: true
      validateCertificateName: true
    }
  }
}

// NOTE: The MCP server is registered via the Azure Portal using APIM's native
// "Expose an existing MCP server" feature (APIs > MCP Servers > + Create MCP server).
// This is not yet available as an ARM/Bicep resource type.
// See AZURE_DEPLOYMENT.md for portal setup instructions.

// Product for subscription management
resource mcpProduct 'Microsoft.ApiManagement/service/products@2023-09-01-preview' = {
  parent: apim
  name: 'databricks-mcp'
  properties: {
    displayName: 'Databricks MCP Access'
    description: 'Access to the Databricks Error Logs MCP Server'
    subscriptionRequired: true
    approvalRequired: false
    state: 'published'
  }
}

output gatewayUrl string = apim.properties.gatewayUrl
output apimName string = apim.name
output backendUrl string = backendUrl
