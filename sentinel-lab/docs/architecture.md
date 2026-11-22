# Architecture

Current state of the Microsoft Sentinel Detection Lab. Solid lines are live today; dashed boxes are on the roadmap.

## Data flow: from activity to incident to email

```mermaid
flowchart LR
    subgraph SRC["Log sources"]
        direction TB
        SUB["Azure subscription<br/>Activity Log"]
        ENTRA["Microsoft Entra ID<br/>tenant audit logs"]
        VM["Windows VM<br/>security events<br/>(planned)"]:::planned
    end

    subgraph RG["Resource group: rg-sentinel-lab (germanywestcentral)"]
        direction LR

        subgraph LAW["Log Analytics workspace: log-sentinel-lab<br/>90-day retention · 1 GB/day cap"]
            direction TB
            T1[("AzureActivity")]
            T2[("AuditLogs")]
            T3[("SecurityEvent<br/>(planned)")]:::planned
        end

        subgraph SEN["Microsoft Sentinel"]
            direction TB
            R1["Rule: New Azure RBAC role assignment<br/>T1098 · High/Medium"]
            R2["Rule: Security logging or detection tampering<br/>T1562 · High"]
            R3["Rule: User added to Entra ID directory role<br/>T1098.003 · High/Medium"]
            INC["Incidents"]
            AR["Automation rule<br/>Email on every new incident"]
        end

        subgraph PB["Playbook: Logic App pb-incident-email"]
            direction TB
            TRIG["Trigger: Sentinel incident<br/>(managed identity)"]
            MAIL["Action: Send an email (V2)<br/>Outlook connection"]
            TRIG --> MAIL
        end
    end

    ANALYST(["SOC analyst inbox<br/>notificationEmail"])

    SUB -- "diagnostic setting<br/>activity-to-sentinel" --> T1
    ENTRA -- "diagnostic setting<br/>entra-to-sentinel" --> T2
    VM -. "Azure Monitor Agent + DCR" .-> T3

    T1 --> R1
    T1 --> R2
    T2 --> R3
    R1 --> INC
    R2 --> INC
    R3 --> INC
    INC --> AR
    AR --> TRIG
    MAIL --> ANALYST

    classDef planned stroke-dasharray: 5 5,opacity:0.6
```

**How it works**

1. The subscription **Activity Log** and the Entra ID **audit logs** are forwarded to the workspace by diagnostic settings, landing in the `AzureActivity` and `AuditLogs` tables.
2. Three **scheduled analytics rules** run every hour over the last hour of data. Each rule's KQL lives once in [`detections/`](../detections/) and is loaded into Bicep with `loadTextContent()`.
3. Every match becomes an alert and an **incident**. The RBAC and Entra rules set severity per alert from a `Severity` column (High for privileged roles, Medium otherwise).
4. The **automation rule** runs the **`pb-incident-email`** playbook on every new incident. The playbook authenticates to Sentinel with its system-assigned managed identity and sends the incident title, severity, description and link through Outlook.

## Deployment: how the code becomes resources

```mermaid
flowchart LR
    subgraph REPO["GitHub repo: sentinel-lab/"]
        direction TB
        MAIN["infra/main.bicep<br/>(subscription scope)"]
        MOD1["infra/modules/sentinel.bicep"]
        MOD2["infra/modules/analytics-rules.bicep"]
        KQL["detections/*.kql"]
        PBB["playbooks/pb-incident-email.bicep"]
        MAIN --> MOD1
        MAIN --> MOD2
        KQL -- "loadTextContent()" --> MOD2
    end

    CLI["Azure CLI<br/>az deployment sub create"]
    CLIRG["Azure CLI<br/>az deployment group create"]
    REST["Azure CLI<br/>az rest (tenant scope)"]
    PORTAL["Azure portal<br/>(manual)"]
    GHA["GitHub Actions<br/>lint → what-if → deploy<br/>(planned)"]:::planned

    subgraph AZ["Azure"]
        direction TB
        A1["Resource group, workspace,<br/>Sentinel, analytics rules,<br/>Activity Log diagnostic setting"]
        A2["Logic App playbook"]
        A3["Entra ID diagnostic setting"]
        A4["Automation rule, API connection<br/>authorization, budget alerts"]
    end

    MAIN --> CLI --> A1
    PBB --> CLIRG --> A2
    REST --> A3
    PORTAL --> A4
    REPO -.-> GHA -.-> A1

    classDef planned stroke-dasharray: 5 5,opacity:0.6
```

| What | Deployed by | Why not in Bicep (yet) |
|---|---|---|
| Resource group, workspace, Sentinel, 3 analytics rules, Activity Log export | `infra/main.bicep` | n/a |
| Logic App `pb-incident-email` | `playbooks/pb-incident-email.bicep` (resource-group scope) | n/a |
| Entra ID diagnostic setting | `az rest` | Tenant-scope resource that needs Global Administrator |
| Automation rule, Outlook connection sign-in, budget | Portal | The Outlook API connection needs an interactive OAuth consent |

## Cost and security controls

- **Ingestion cap:** 1 GB/day on the workspace, plus a subscription budget with alerts at 50 %, 80 % and 100 %.
- **No secrets in code:** the playbook uses a managed identity for Sentinel, and the recipient address and subscription ID are parameters, not hard-coded values.
- **Disposable:** `az group delete --name rg-sentinel-lab` plus removing the two diagnostic settings tears the whole lab down; it can be rebuilt from code in minutes.
