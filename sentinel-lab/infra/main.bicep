// main.bicep - Sentinel Lab, step 1
// Creates: resource group + Log Analytics workspace + Microsoft Sentinel
// Deploy at subscription scope (see README / deploy command).

targetScope = 'subscription'

@description('Azure region for all resources')
param location string = 'germanywestcentral'

@description('Short name used in all resource names')
param projectName string = 'sentinel-lab'

@description('Days to keep logs (Sentinel includes 90 days at no extra retention cost)')
@minValue(30)
@maxValue(90)
param retentionInDays int = 90

@description('Daily ingestion cap in GB to protect your budget (-1 = no cap)')
param dailyQuotaGb int = 1

var tags = {
  project: projectName
  environment: 'lab'
  managedBy: 'bicep'
}

resource rg 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: 'rg-${projectName}'
  location: location
  tags: tags
}

module sentinel 'modules/sentinel.bicep' = {
  name: 'sentinel-deployment'
  scope: rg
  params: {
    location: location
    workspaceName: 'log-${projectName}'
    retentionInDays: retentionInDays
    dailyQuotaGb: dailyQuotaGb
    tags: tags
  }
}

// Detection rules (KQL loaded from /detections)
module analyticsRules 'modules/analytics-rules.bicep' = {
  name: 'analytics-rules-deployment'
  scope: rg
  params: {
    workspaceName: sentinel.outputs.workspaceName
  }
}

// Data source 1: send the subscription's Activity Log to the Sentinel workspace
resource activityLogToSentinel 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'activity-to-sentinel'
  properties: {
    workspaceId: sentinel.outputs.workspaceId
    logs: [for category in [
      'Administrative'
      'Security'
      'ServiceHealth'
      'Alert'
      'Recommendation'
      'Policy'
      'Autoscale'
      'ResourceHealth'
    ]: {
      category: category
      enabled: true
    }]
  }
}

output resourceGroupName string = rg.name
output workspaceName string = sentinel.outputs.workspaceName
output workspaceId string = sentinel.outputs.workspaceId
