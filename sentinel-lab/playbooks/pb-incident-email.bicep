param workflows_pb_incident_email_name string = 'pb-incident-email'

@description('Recipient address for Sentinel incident notification emails.')
param notificationEmail string = 'your-email@example.com'

param connections_azuresentinel_pb_incident_email_externalid string = '/subscriptions/${subscription().subscriptionId}/resourceGroups/rg-sentinel-lab/providers/Microsoft.Web/connections/azuresentinel-pb-incident-email'
param connections_outlook_externalid string = '/subscriptions/${subscription().subscriptionId}/resourceGroups/rg-sentinel-lab/providers/Microsoft.Web/connections/outlook'

resource workflows_pb_incident_email_name_resource 'Microsoft.Logic/workflows@2019-05-01' = {
  name: workflows_pb_incident_email_name
  location: 'germanywestcentral'
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
            id: '/subscriptions/${subscription().subscriptionId}/providers/Microsoft.Web/locations/germanywestcentral/managedApis/azuresentinel'
            connectionId: connections_azuresentinel_pb_incident_email_externalid
            connectionName: 'azuresentinel-${workflows_pb_incident_email_name}'
            connectionProperties: {
              authentication: {
                type: 'ManagedServiceIdentity'
              }
            }
          }
          outlook: {
            id: '/subscriptions/${subscription().subscriptionId}/providers/Microsoft.Web/locations/germanywestcentral/managedApis/outlook'
            connectionId: connections_outlook_externalid
            connectionName: 'outlook'
            connectionProperties: {}
          }
        }
      }
    }
  }
}

resource workflows_pb_incident_email_name_default 'Microsoft.Logic/workflows/accessKeys@2015-02-01-preview' = {
  parent: workflows_pb_incident_email_name_resource
  name: 'default'
  properties: {}
}
