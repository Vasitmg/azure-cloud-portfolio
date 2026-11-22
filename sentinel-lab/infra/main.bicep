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

@description('Deploy the Windows test VM (false in the pipeline, true only for a test session)')
param deployVm bool = false

@secure()
@description('Local admin password for the test VM (only needed when deployVm is true)')
param vmAdminPassword string = ''

@description('Size of the test VM (change if a size has no capacity in the region)')
param vmSize string = 'Standard_B2s_v2'

@description('Region for the test VM (the workspace stays in location)')
param vmLocation string = location

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

// Data source 3 (optional): Windows VM with Security events via Azure Monitor Agent
module testVm 'modules/vm.bicep' = if (deployVm) {
  name: 'vm-deployment'
  scope: rg
  params: {
    location: location
    workspaceId: sentinel.outputs.workspaceId
    adminPassword: vmAdminPassword
    vmSize: vmSize
    vmLocation: vmLocation
    tags: tags
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
