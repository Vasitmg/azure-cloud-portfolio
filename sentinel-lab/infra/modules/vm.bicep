// modules/vm.bicep
// Windows test VM that sends Security events to the Sentinel workspace.
// - No public IP, no inbound ports (NSG without allow rules)
// - Azure Monitor Agent + data collection rule (DCR) for Security events
// - Auto-shutdown every evening to save credit
// Deployed only when main.bicep is called with deployVm=true.

@description('Region of the Log Analytics workspace (the DCR stays here)')
param location string

@description('Region for the VM and its network (can differ from the workspace region)')
param vmLocation string = location
param workspaceId string
param tags object

@description('Local admin user name for the VM')
param adminUsername string = 'labadmin'

@secure()
@description('Local admin password (never stored in the repo)')
param adminPassword string

param vmName string = 'vm-lab-win01'
param vmSize string = 'Standard_B2s_v2'

@description('Daily auto-shutdown time (24h, W. Europe time)')
param autoShutdownTime string = '2200'

resource nsg 'Microsoft.Network/networkSecurityGroups@2023-11-01' = {
  name: 'nsg-lab'
  location: vmLocation
  tags: tags
  properties: {
    securityRules: [] // no inbound allow rules: the VM is not reachable from the internet
  }
}

resource vnet 'Microsoft.Network/virtualNetworks@2023-11-01' = {
  name: 'vnet-lab'
  location: vmLocation
  tags: tags
  properties: {
    addressSpace: {
      addressPrefixes: ['10.10.0.0/16']
    }
    subnets: [
      {
        name: 'snet-lab'
        properties: {
          addressPrefix: '10.10.1.0/24'
          networkSecurityGroup: { id: nsg.id }
        }
      }
    ]
  }
}

resource nic 'Microsoft.Network/networkInterfaces@2023-11-01' = {
  name: 'nic-${vmName}'
  location: vmLocation
  tags: tags
  properties: {
    ipConfigurations: [
      {
        name: 'ipconfig1'
        properties: {
          subnet: { id: vnet.properties.subnets[0].id }
          privateIPAllocationMethod: 'Dynamic'
        }
      }
    ]
  }
}

resource vm 'Microsoft.Compute/virtualMachines@2024-03-01' = {
  name: vmName
  location: vmLocation
  tags: tags
  identity: {
    type: 'SystemAssigned' // required by the Azure Monitor Agent
  }
  properties: {
    hardwareProfile: { vmSize: vmSize }
    osProfile: {
      computerName: vmName
      adminUsername: adminUsername
      adminPassword: adminPassword
      windowsConfiguration: {
        provisionVMAgent: true
        enableAutomaticUpdates: true
      }
    }
    storageProfile: {
      imageReference: {
        publisher: 'MicrosoftWindowsServer'
        offer: 'WindowsServer'
        sku: '2022-datacenter-azure-edition'
        version: 'latest'
      }
      osDisk: {
        createOption: 'FromImage'
        deleteOption: 'Delete'
        managedDisk: { storageAccountType: 'StandardSSD_LRS' }
      }
    }
    networkProfile: {
      networkInterfaces: [
        {
          id: nic.id
          properties: { deleteOption: 'Delete' }
        }
      ]
    }
  }
}

resource ama 'Microsoft.Compute/virtualMachines/extensions@2024-03-01' = {
  parent: vm
  name: 'AzureMonitorWindowsAgent'
  location: vmLocation
  properties: {
    publisher: 'Microsoft.Azure.Monitor'
    type: 'AzureMonitorWindowsAgent'
    typeHandlerVersion: '1.0'
    autoUpgradeMinorVersion: true
    enableAutomaticUpgrade: true
  }
}

// Which events to collect: logons (4624), failed logons (4625),
// special privileges (4672), new user (4720), user added to local group (4732)
resource dcr 'Microsoft.Insights/dataCollectionRules@2022-06-01' = {
  name: 'dcr-windows-security-events'
  location: location
  tags: tags
  kind: 'Windows'
  properties: {
    dataSources: {
      windowsEventLogs: [
        {
          name: 'securityEvents'
          streams: ['Microsoft-SecurityEvent']
          xPathQueries: [
            'Security!*[System[(EventID=4624 or EventID=4625 or EventID=4672 or EventID=4720 or EventID=4732)]]'
          ]
        }
      ]
    }
    destinations: {
      logAnalytics: [
        {
          name: 'sentinelWorkspace'
          workspaceResourceId: workspaceId
        }
      ]
    }
    dataFlows: [
      {
        streams: ['Microsoft-SecurityEvent']
        destinations: ['sentinelWorkspace']
      }
    ]
  }
}

resource dcrAssociation 'Microsoft.Insights/dataCollectionRuleAssociations@2022-06-01' = {
  name: 'dcra-security-events'
  scope: vm
  properties: {
    dataCollectionRuleId: dcr.id
  }
  dependsOn: [ama]
}

resource autoShutdown 'Microsoft.DevTestLab/schedules@2018-09-15' = {
  name: 'shutdown-computevm-${vmName}'
  location: vmLocation
  tags: tags
  properties: {
    status: 'Enabled'
    taskType: 'ComputeVmShutdownTask'
    dailyRecurrence: { time: autoShutdownTime }
    timeZoneId: 'W. Europe Standard Time'
    targetResourceId: vm.id
    notificationSettings: { status: 'Disabled' }
  }
}

output vmName string = vm.name
