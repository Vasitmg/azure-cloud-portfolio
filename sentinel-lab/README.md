# Microsoft Sentinel Detection Lab

A hands-on security operations lab on Microsoft Azure. Everything is deployed as **Infrastructure as Code (Bicep)**, and the detection rules are written in **KQL** and kept in version control.

> **Status:** 🚧 Work in progress. Infrastructure and the first data source are live; more data sources and detections are being added.

## Goals

- Build a working SIEM with Microsoft Sentinel from scratch, without clicking resources together in the portal
- Collect real security telemetry (Azure Activity, Microsoft Entra ID, Windows security events)
- Write and test my own detection rules mapped to MITRE ATT&CK
- Automate the response to incidents with playbooks
- Deploy everything through a CI/CD pipeline (GitHub Actions)

## Architecture

```
Azure subscription
│
├── Activity Log ──(diagnostic setting)──┐
│                                        ▼
└── rg-sentinel-lab               Log Analytics workspace (log-sentinel-lab)
                                         │
                                         ▼
                                  Microsoft Sentinel
                                  ├── Analytics rules (KQL)  → detections/
                                  ├── Incidents
                                  └── Playbooks (Logic Apps) → playbooks/
```

_A proper diagram will be added to `docs/`._

## What is deployed

| Component | Resource | Defined in |
|---|---|---|
| Resource group | `rg-sentinel-lab` | `infra/main.bicep` |
| Log Analytics workspace | `log-sentinel-lab` (90-day retention, 1 GB/day cap) | `infra/modules/sentinel.bicep` |
| Microsoft Sentinel | enabled on the workspace | `infra/modules/sentinel.bicep` |
| Data source: Azure Activity | subscription diagnostic setting `activity-to-sentinel` | `infra/main.bicep` |
| Playbook | Logic App `pb-incident-email` + automation rule "Email on every new incident" | `playbooks/` |
| Data source: Entra ID audit logs | tenant diagnostic setting `entra-to-sentinel` | `az rest` (tenant scope, see below) |

## Repository structure

```
sentinel-lab/
├── infra/        Bicep templates (main.bicep + modules)
├── detections/   KQL detection rules
├── playbooks/    Logic App playbooks for automated response
├── docs/         Diagrams and screenshots
└── README.md
```

## Deploy it yourself

**Prerequisites:** an Azure subscription, the [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli) and Bicep (`az bicep install`).

```bash
# 1. Sign in
az login

# 2. Register the resource providers (one time per subscription)
az provider register --namespace Microsoft.OperationalInsights
az provider register --namespace Microsoft.OperationsManagement
az provider register --namespace Microsoft.SecurityInsights
az provider register --namespace Microsoft.Insights

# 3. Preview the changes
az deployment sub what-if --location germanywestcentral \
  --template-file infra/main.bicep

# 4. Deploy
az deployment sub create --location germanywestcentral \
  --template-file infra/main.bicep
```

**Entra ID audit logs** (tenant level, needs Global Administrator):

```bash
WS_ID=$(az monitor log-analytics workspace show -g rg-sentinel-lab -n log-sentinel-lab --query id -o tsv)
az rest --method put \
  --url "https://management.azure.com/providers/microsoft.aadiam/diagnosticSettings/entra-to-sentinel?api-version=2017-04-01" \
  --body "{\"properties\":{\"workspaceId\":\"$WS_ID\",\"logs\":[{\"category\":\"AuditLogs\",\"enabled\":true}]}}"
```

**Tear down** (to stop all costs):

```bash
az group delete --name rg-sentinel-lab
az monitor diagnostic-settings subscription delete --name activity-to-sentinel
```

## Detections

| Rule | Data source | MITRE ATT&CK | File |
|---|---|---|---|
| New Azure RBAC role assignment | AzureActivity | T1098 Account Manipulation | [`role-assignment-created.kql`](detections/role-assignment-created.kql) |
| Security logging or detection tampering | AzureActivity | T1562 Impair Defenses | [`security-logging-tampering.kql`](detections/security-logging-tampering.kql) |
| User added to Entra ID directory role | AuditLogs | T1098.003 Additional Cloud Roles | [`entra-privileged-role-assigned.kql`](detections/entra-privileged-role-assigned.kql) |

## Cost control

- Daily ingestion cap of 1 GB on the workspace
- Budget with email alerts at 50 %, 80 % and 100 % on the subscription
- The whole lab can be deleted and rebuilt from code in a few minutes

## Lessons learned

- **Resource providers must be registered first.** On a new subscription, enabling Sentinel failed with `MissingSubscriptionRegistration` for `Microsoft.OperationsManagement`. Registering the providers once fixed it, so the step is now part of the deploy instructions.
- **Activity Log events come in pairs.** A role assignment is logged as a `Start` event and a `Success` event with the same `CorrelationId`. Only the `Start` event contains the request body with the role and the principal. My first detection read the `Success` event only, so the role was always empty and every assignment was rated "Medium" (an Owner assignment would have been missed as high severity). Joining both events on `CorrelationId` fixed it. Lesson: always inspect the raw event (`bag_keys(Properties_d)`) before writing parsing logic.

## Roadmap

- [x] Log Analytics workspace + Microsoft Sentinel via Bicep
- [x] Azure Activity data source
- [x] Microsoft Entra ID audit logs
- [ ] Windows VM with security events (Azure Monitor Agent + data collection rule)
- [ ] 3–5 custom detection rules deployed as code
- [x] Playbook: email notification on every new incident (Logic App + automation rule)
- [ ] Playbook: disable user on high-severity incident
- [ ] GitHub Actions pipeline: lint → what-if → deploy
- [ ] Architecture diagram and screenshots in `docs/`