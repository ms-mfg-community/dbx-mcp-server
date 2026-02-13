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

// Backend pointing to the Container App
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

// API definition for the MCP endpoint
resource mcpApi 'Microsoft.ApiManagement/service/apis@2023-09-01-preview' = {
  parent: apim
  name: 'databricks-mcp'
  properties: {
    displayName: 'Databricks Error Logs MCP'
    description: 'MCP server for searching Databricks error logs'
    path: ''
    protocols: [
      'https'
    ]
    subscriptionRequired: true
    subscriptionKeyParameterNames: {
      header: 'Ocp-Apim-Subscription-Key'
      query: 'subscription-key'
    }
  }
}

// Catch-all operation for MCP protocol (JSON-RPC over HTTP)
resource mcpOperation 'Microsoft.ApiManagement/service/apis/operations@2023-09-01-preview' = {
  parent: mcpApi
  name: 'mcp-endpoint'
  properties: {
    displayName: 'MCP Endpoint'
    method: 'POST'
    urlTemplate: '/mcp'
    description: 'MCP streamable-http endpoint (JSON-RPC)'
  }
}

// GET operation for MCP SSE stream
resource mcpGetOperation 'Microsoft.ApiManagement/service/apis/operations@2023-09-01-preview' = {
  parent: mcpApi
  name: 'mcp-endpoint-get'
  properties: {
    displayName: 'MCP SSE Stream'
    method: 'GET'
    urlTemplate: '/mcp'
    description: 'MCP server-sent events stream endpoint'
  }
}

// DELETE operation for MCP session cleanup
resource mcpDeleteOperation 'Microsoft.ApiManagement/service/apis/operations@2023-09-01-preview' = {
  parent: mcpApi
  name: 'mcp-endpoint-delete'
  properties: {
    displayName: 'MCP Session Cleanup'
    method: 'DELETE'
    urlTemplate: '/mcp'
    description: 'MCP session cleanup endpoint'
  }
}

// Policy: forward to backend, rate limit, forward Databricks headers
resource mcpApiPolicy 'Microsoft.ApiManagement/service/apis/policies@2023-09-01-preview' = {
  parent: mcpApi
  name: 'policy'
  properties: {
    format: 'xml'
    value: '''
<policies>
  <inbound>
    <base />
    <set-backend-service backend-id="mcp-server-backend" />
    <rate-limit calls="60" renewal-period="60" />
    <set-header name="X-Forwarded-For" exists-action="skip">
      <value>@(context.Request.IpAddress)</value>
    </set-header>
  </inbound>
  <backend>
    <forward-request timeout="120" follow-redirects="true" buffer-response="false" />
  </backend>
  <outbound>
    <base />
    <!-- Strip sensitive token from response headers -->
    <set-header name="X-Databricks-Token" exists-action="delete" />
  </outbound>
  <on-error>
    <base />
  </on-error>
</policies>
'''
  }
}

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

// Link the API to the product
resource productApi 'Microsoft.ApiManagement/service/products/apis@2023-09-01-preview' = {
  parent: mcpProduct
  name: mcpApi.name
}

output gatewayUrl string = apim.properties.gatewayUrl
output apimName string = apim.name
