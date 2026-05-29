@description('Short prefix used to name the three resources. 3-12 lowercase letters/digits.')
@minLength(3)
@maxLength(12)
param namePrefix string = 'cc${uniqueString(resourceGroup().id)}'

var location           = resourceGroup().location

var aoaiAccountName    = '${namePrefix}-aoai'
var cacheAccountName   = '${namePrefix}-cache'
var cacheContainerName = 'default-container'
var aoaiDeploymentName = 'context-cache-deployment'
var modelName          = 'gpt-5.4'
var modelVersion       = '2026-03-05-contextcache'
var tags = {
  sample: 'azure-context-cache-quickstart'
  environment: 'demo'
}

resource aoai 'Microsoft.CognitiveServices/accounts@2024-10-01' = {
  name: aoaiAccountName
  location: location
  tags: tags
  kind: 'OpenAI'
  sku: { name: 'S0' }
  properties: {
    customSubDomainName: aoaiAccountName
    publicNetworkAccess: 'Enabled'
  }
}

resource cacheAccount 'Microsoft.AzureContextCache/accounts@2026-01-01-preview' = {
  name: cacheAccountName
  location: location
  tags: tags
  properties: {
    accountKind: 'Regional'
    description: 'Context Cache account (azure-context-cache-quickstart)'
  }
}

resource cacheContainer 'Microsoft.AzureContextCache/accounts/containers@2026-01-01-preview' = {
  parent: cacheAccount
  name: cacheContainerName
  properties: {
    description: 'Prompt cache container for ${modelName}'
    modelName: modelName
    provider: 'OpenAI'
    timeToLive: 7
  }
}

resource aoaiDeployment 'Microsoft.CognitiveServices/accounts/deployments@2026-03-15-preview' = {
  parent: aoai
  name: aoaiDeploymentName
  sku: {
    name: 'Standard'
    capacity: 100
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: modelName
      version: modelVersion
    }
    contextCacheContainerId: cacheContainer.id
  }
}

output azureOpenAIAccountName string  = aoai.name
output azureOpenAIEndpoint string     = aoai.properties.endpoint
output aoaiDeploymentName string      = aoaiDeployment.name
output contextCacheAccountName string = cacheAccount.name
output contextCacheContainerId string = cacheContainer.id
output modelName string               = modelName
output modelVersion string            = modelVersion
