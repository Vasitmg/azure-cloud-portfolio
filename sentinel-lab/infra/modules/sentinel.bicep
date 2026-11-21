// modules/sentinel.bicep
// Log Analytics workspace with Microsoft Sentinel enabled on top of it.

param location string
param workspaceName string
param retentionInDays int
param dailyQuotaGb int
param tags object

resource workspace 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: workspaceName
  location: location
  tags: tags
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: retentionInDays
    workspaceCapping: {
      dailyQuotaGb: dailyQuotaGb
    }
  }
}

// Enables Microsoft Sentinel on the workspace
resource sentinelOnboarding 'Microsoft.SecurityInsights/onboardingStates@2024-03-01' = {
  name: 'default'
  scope: workspace
  properties: {}
}

output workspaceName string = workspace.name
output workspaceId string = workspace.id
