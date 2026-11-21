// modules/analytics-rules.bicep
// Scheduled analytics rules for Microsoft Sentinel.
// The KQL lives in /detections and is loaded at build time,
// so every query exists exactly once in the repo.

param workspaceName string

resource workspace 'Microsoft.OperationalInsights/workspaces@2023-09-01' existing = {
  name: workspaceName
}

// Rule 1: new Azure RBAC role assignment
resource roleAssignmentRule 'Microsoft.SecurityInsights/alertRules@2024-03-01' = {
  name: guid(workspace.id, 'role-assignment-created-v2')
  scope: workspace
  kind: 'Scheduled'
  properties: {
    displayName: 'New Azure RBAC role assignment'
    description: 'Detects a successful Azure role assignment. Owner, Contributor and User Access Administrator are rated High, all other roles Medium. Attackers grant roles to keep access (MITRE T1098).'
    enabled: true
    query: loadTextContent('../../detections/role-assignment-created.kql')
    queryFrequency: 'PT1H'
    queryPeriod: 'PT1H'
    triggerOperator: 'GreaterThan'
    triggerThreshold: 0
    severity: 'Medium' // default; overridden per alert by the Severity column below
    suppressionEnabled: false
    suppressionDuration: 'PT1H'
    tactics: [
      'Persistence'
      'PrivilegeEscalation'
    ]
    techniques: [
      'T1098'
    ]
    eventGroupingSettings: {
      aggregationKind: 'AlertPerResult'
    }
    alertDetailsOverride: {
      alertDisplayNameFormat: 'Role assignment by {{Caller}} (role {{RoleGuid}})'
      alertSeverityColumnName: 'Severity'
    }
    entityMappings: [
      {
        entityType: 'Account'
        fieldMappings: [
          {
            identifier: 'FullName'
            columnName: 'Caller'
          }
        ]
      }
      {
        entityType: 'IP'
        fieldMappings: [
          {
            identifier: 'Address'
            columnName: 'CallerIpAddress'
          }
        ]
      }
    ]
    incidentConfiguration: {
      createIncident: true
      groupingConfiguration: {
        enabled: false
        reopenClosedIncident: false
        lookbackDuration: 'PT5H'
        matchingMethod: 'AllEntities'
      }
    }
  }
}

// Rule 2: security logging or detection tampering
resource loggingTamperingRule 'Microsoft.SecurityInsights/alertRules@2024-03-01' = {
  name: guid(workspace.id, 'security-logging-tampering')
  scope: workspace
  kind: 'Scheduled'
  properties: {
    displayName: 'Security logging or detection tampering'
    description: 'Detects deletion of diagnostic settings, the Log Analytics workspace, Sentinel analytics rules, data connectors or automation rules. Attackers do this to blind defenders (MITRE T1562).'
    enabled: true
    query: loadTextContent('../../detections/security-logging-tampering.kql')
    queryFrequency: 'PT1H'
    queryPeriod: 'PT1H'
    triggerOperator: 'GreaterThan'
    triggerThreshold: 0
    severity: 'High'
    suppressionEnabled: false
    suppressionDuration: 'PT1H'
    tactics: [
      'DefenseEvasion'
    ]
    techniques: [
      'T1562'
    ]
    eventGroupingSettings: {
      aggregationKind: 'AlertPerResult'
    }
    alertDetailsOverride: {
      alertDisplayNameFormat: '{{Action}} deleted by {{Caller}}'
    }
    entityMappings: [
      {
        entityType: 'Account'
        fieldMappings: [
          {
            identifier: 'FullName'
            columnName: 'Caller'
          }
        ]
      }
      {
        entityType: 'IP'
        fieldMappings: [
          {
            identifier: 'Address'
            columnName: 'CallerIpAddress'
          }
        ]
      }
      {
        entityType: 'AzureResource'
        fieldMappings: [
          {
            identifier: 'ResourceId'
            columnName: 'TargetResource'
          }
        ]
      }
    ]
    incidentConfiguration: {
      createIncident: true
      groupingConfiguration: {
        enabled: false
        reopenClosedIncident: false
        lookbackDuration: 'PT5H'
        matchingMethod: 'AllEntities'
      }
    }
  }
}
