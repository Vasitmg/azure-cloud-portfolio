# Azure Cloud Portfolio

Hands-on Azure security projects focused on **identity security, threat detection and monitoring**. Everything is built as code (Bicep, KQL, Logic Apps) and tested against real activity in my own Azure tenant.

---

## 📂 Projects

### 1️⃣ Microsoft Sentinel Detection Lab — 🚧 in progress

A working SIEM built from scratch with Infrastructure as Code.

- Log Analytics workspace + Microsoft Sentinel deployed with **Bicep**
- Data sources: **Azure Activity Log** and **Microsoft Entra ID audit logs**
- **3 custom detection rules** in KQL, mapped to MITRE ATT&CK and deployed as code
  - New Azure RBAC role assignment (T1098)
  - Security logging or detection tampering (T1562)
  - User added to an Entra ID directory role (T1098.003)
- **Automated response:** Logic App playbook that emails on every new incident
- Cost controls: daily ingestion cap and budget alerts

📁 [`sentinel-lab/`](sentinel-lab/)

---

### 2️⃣ Azure Security Monitoring baseline — planned

- Azure Monitor alert rules and action groups
- Defender for Cloud recommendations and secure score
- Azure Policy for security governance

---

## 🛡 Focus areas

- Identity & Access Management (Entra ID, RBAC)
- Threat detection engineering (KQL, MITRE ATT&CK)
- Security monitoring and automated response (SOAR)
- Infrastructure as Code (Bicep) and CI/CD
- Security governance and cost control

---

## 🚀 Roadmap

- [x] Microsoft Sentinel lab: infrastructure, data sources, first detections, playbook
- [ ] Windows VM with security events and endpoint detections
- [ ] GitHub Actions pipeline: lint → what-if → deploy
- [ ] Conditional Access and identity protection scenarios
- [ ] Architecture diagrams and decision records for each project