// modules/playbook.bicep
// Incident email playbook (Logic App) + Sentinel automation rule that runs it.
//
// Prerequisite (one-time, manual): the two API connections already exist in the
// resource group, because the Outlook.com connection needs an interactive sign-in:
//   - azuresentinel-pb-incident-email  (Microsoft Sentinel, managed identity)
//   - outlook                          (Outlook.com, signed in by the owner)
// Sentinel also needs "playbook permissions" on the resource group (granted once
// in Sentinel > Settings).

param location string
param workspaceName string

@description('Recipient for incident emails (passed in by the pipeline, never stored in the repo)')
param notificationEmail string

param playbookName string = 'pb-incident-email'

resource workspace 'Microsoft.OperationalInsights/workspaces@2023-09-01' existing = {
  name: workspaceName
}

resource sentinelConnection 'Microsoft.Web/connections@2016-06-01' existing = {
  name: 'azuresentinel-${playbookName}'
}

resource outlookConnection 'Microsoft.Web/connections@2016-06-01' existing = {
  name: 'outlook'
}

resource playbook 'Microsoft.Logic/workflows@2019-05-01' = {
  name: playbookName
  location: location
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    state: 'Enabled'
    definition: {
      '$schema': 'https://schema.management.azure.com/providers/Microsoft.Logic/schemas/2016-06-01/workflowdefinition.json#'
      contentVersion: '1.0.0.0'
      parameters: {
        '$connections': {
          defaultValue: {}
          type: 'Object'
        }
      }
      triggers: {
        Microsoft_Sentinel_incident: {
          type: 'ApiConnectionWebhook'
          inputs: {
            host: {
              connection: {
                name: '@parameters(\'$connections\')[\'azuresentinel\'][\'connectionId\']'
              }
            }
            body: {
              callback_url: '@{listCallbackUrl()}'
            }
            path: '/incident-creation'
          }
        }
      }
      actions: {
        'Send_an_email_(V2)': {
          runAfter: {}
          type: 'ApiConnection'
          inputs: {
            host: {
              connection: {
                name: '@parameters(\'$connections\')[\'outlook\'][\'connectionId\']'
              }
            }
            method: 'post'
            body: {
              To: notificationEmail
              Subject: 'Sentinel - @{triggerBody()?[\'object\']?[\'properties\']?[\'severity\']} - @{triggerBody()?[\'object\']?[\'properties\']?[\'title\']}'
              Body: '<br><p class="editor-paragraph">@{triggerBody()?[\'object\']?[\'properties\']?[\'description\']}</p><br><p class="editor-paragraph">URL: @{triggerBody()?[\'object\']?[\'properties\']?[\'incidentUrl\']}</p>'
              Importance: 'Normal'
            }
            path: '/v2/Mail'
          }
        }
      }
      outputs: {}
    }
    parameters: {
      '$connections': {
        value: {
          azuresentinel: {
            id: subscriptionResourceId('Microsoft.Web/locations/managedApis', location, 'azuresentinel')
            connectionId: sentinelConnection.id
            connectionName: sentinelConnection.name
            connectionProperties: {
              authentication: {
                type: 'ManagedServiceIdentity'
              }
            }
          }
          outlook: {
            id: subscriptionResourceId('Microsoft.Web/locations/managedApis', location, 'outlook')
            connectionId: outlookConnection.id
            connectionName: outlookConnection.name
          }
        }
      }
    }
  }
}

// Runs the playbook for every new incident
resource emailAutomationRule 'Microsoft.SecurityInsights/automationRules@2024-03-01' = {
  name: guid(workspace.id, 'automation-email-on-incident')
  scope: workspace
  properties: {
    displayName: 'Email on every new incident'
    order: 1
    triggeringLogic: {
      isEnabled: true
      triggersOn: 'Incidents'
      triggersWhen: 'Created'
      conditions: []
    }
    actions: [
      {
        order: 1
        actionType: 'RunPlaybook'
        actionConfiguration: {
          logicAppResourceId: playbook.id
          tenantId: tenant().tenantId
        }
      }
    ]
  }
}

output playbookId string = playbook.id
