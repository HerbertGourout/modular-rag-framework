# Claude Code Enterprise Deployment

Complete guide for IT teams deploying Claude Code at scale in organizations.

> **Corrected 2026-08-06** (documentation-utility pass): none of this is configured in this
> project — there is no MDM enrollment, Group Policy object, or `managed-settings.json` anywhere
> in this repository or its infrastructure.
>
> Nothing here was verified against Claude Code's actual enterprise-deployment behavior from
> this environment (no network access to confirm field names like `forceLoginOrgUUID`,
> `policyHelper`, `requiredMaximumVersion`, or the `/status`/`/doctor` command output shown
> below). Treat this file as unverified illustrative material for a hypothetical future rollout,
> not a description of anything this project does today.
>
> One concrete, cross-checked issue: "Policy 3" (`30-dev-team.json`) uses
> `allowedMcpServers`/`deniedMcpServers`/`allowManagedMcpServersOnly` — the same MCP field
> vocabulary already flagged as unverified/likely-invented in
> [claude-code-mcp-setup.md](claude-code-mcp-setup.md) and corrected in
> [mcp-integrations.md](mcp-integrations.md) (whose confirmed-real fields are only
> `command`/`args`/`env` for local servers or `type`/`url` for remote ones, per `.mcp.json`).

**Table of Contents**
1. [Managed Settings Deployment](#managed-settings-deployment) — Distribution methods
2. [MDM Setup](#mdm-setup) — macOS/Windows management
3. [Group Policy](#group-policy) — Windows enterprise
4. [Policy Helper](#policy-helper) — Dynamic configuration
5. [Security Policies](#security-policies) — Governance examples
6. [Monitoring & Audit](#monitoring--audit) — Track usage
7. [Examples](#examples) — Real-world deployments

---

## Managed Settings Deployment

### What are Managed Settings?

**Managed settings** are organization-wide policies that:
- ❌ Cannot be overridden by users
- ✅ Enforce compliance/security standards
- ✅ Apply to ALL users on a machine
- ✅ Update automatically

### Deployment Methods

| Method | OS | Priority | Ease | Use Case |
|--------|----|----|------|----------|
| **Server-managed** | All | Highest | Easy | Cloud-based policies |
| **MDM** | macOS | High | Medium | Apple device management |
| **Group Policy** | Windows | High | Medium | Windows Active Directory |
| **File-based** | All | Medium | Medium | Self-hosted environments |

### Managed Settings Locations

**macOS**:
```
/Library/Application Support/ClaudeCode/
├── managed-settings.json
└── managed-settings.d/
    ├── 10-security.json
    └── 20-compliance.json
```

**Linux/WSL**:
```
/etc/claude-code/
├── managed-settings.json
└── managed-settings.d/
    ├── 10-security.json
    └── 20-compliance.json
```

**Windows**:
```
C:\Program Files\ClaudeCode\
├── managed-settings.json
└── managed-settings.d/
    ├── 10-security.json
    └── 20-compliance.json
```

### File-Based Managed Settings

Create `managed-settings.json`:

```json
{
  "forceLoginOrgUUID": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "forceLoginMethod": "claudeai",
  "requiredMinimumVersion": "2.1.150",
  "permissions": {
    "deny": [
      "Read(./.env*)",
      "Read(./secrets/**)",
      "Bash(curl *)"
    ]
  },
  "sandbox": {
    "enabled": true,
    "filesystem": {
      "denyRead": ["~/.ssh", "~/.aws"]
    }
  }
}
```

Deploy to all machines:
```bash
# macOS
sudo cp managed-settings.json /Library/Application\ Support/ClaudeCode/

# Linux
sudo cp managed-settings.json /etc/claude-code/

# Windows (admin)
Copy-Item managed-settings.json "C:\Program Files\ClaudeCode\"
```

### Drop-In Directory

Organize policies by team:

```
/etc/claude-code/managed-settings.d/
├── 10-security-baseline.json       # Core security
├── 20-compliance.json              # Regulatory
├── 30-ml-team-policies.json        # ML team specifics
└── 40-devops-policies.json         # DevOps team specifics
```

**Merge order:** Files sorted alphabetically, merged into single policy.

---

## MDM Setup

### macOS - Jamf

Deploy managed settings via Jamf configuration profile.

**Step 1: Create Configuration Profile**

In Jamf Pro:
1. Settings → Configuration Profiles → New
2. Select "macOS"
3. Search "Claude Code" (or add custom)
4. Add payload: Application Preferences
5. Preference Domain: `com.anthropic.claudecode`

**Step 2: Add Managed Settings**

Paste JSON as preference dictionary:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>forceLoginOrgUUID</key>
    <string>xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx</string>
    <key>forceLoginMethod</key>
    <string>claudeai</string>
    <key>requiredMinimumVersion</key>
    <string>2.1.150</string>
    <key>permissions</key>
    <dict>
        <key>deny</key>
        <array>
            <string>Read(./.env*)</string>
            <string>Bash(curl *)</string>
        </array>
    </dict>
</dict>
</plist>
```

**Step 3: Deploy**
- Assign to device groups
- Select deployment schedule
- Monitor adoption in Jamf

### macOS - Kandji (Iru)

Via Kandji console:

1. **Device Management** → **Settings** → **macOS**
2. Search "Claude Code" or create custom profile
3. Configure managed settings
4. Assign to device groups

---

## Group Policy

### Windows - Group Policy Editor

Deploy via Active Directory Group Policy.

**Step 1: Create Group Policy Object**

On domain controller:
1. Open Group Policy Management
2. Create new GPO: "Claude Code Enterprise Policy"
3. Edit the GPO

**Step 2: Add Registry Policy**

Navigate to:
```
Computer Configuration
  → Policies
    → Administrative Templates
      → [Create new folder] "Claude Code"
        → [Create new policy] "Managed Settings"
```

**Step 3: Configure Policy**

In policy details:
- **Setting name**: Managed Settings (JSON)
- **Supported on**: Windows 10 and later
- **Path**: `HKLM\SOFTWARE\Policies\ClaudeCode`
- **Value name**: `Settings`
- **Value type**: REG_SZ or REG_EXPAND_SZ

**Step 4: Apply**

```json
{
  "forceLoginOrgUUID": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "permissions": {
    "deny": ["Read(./.env*)", "Bash(curl *)"]
  }
}
```

**Step 5: Link and Deploy**

- Link GPO to Organizational Units
- Test with `gpupdate /force`
- Monitor in Group Policy Results

### Windows - Intune

Deploy via Microsoft Intune:

1. **Devices** → **Configuration Profiles** → **Create Profile**
2. Platform: Windows 10/11
3. Profile Type: Custom
4. Add setting:
   - **OMA-URI**: `./Device/Vendor/MSFT/Policy/Config/ClaudeCode~Policy~Settings`
   - **Data Type**: String
   - **Value**: JSON managed settings
5. Assign to device groups
6. Monitor compliance

---

## Policy Helper

### Dynamic Configuration

Use `policyHelper` to compute managed settings at runtime:

```json
{
  "policyHelper": {
    "path": "/usr/local/bin/claude-policy-helper",
    "timeoutMs": 5000,
    "refreshIntervalMs": 3600000
  }
}
```

### Policy Helper Script

**File**: `/usr/local/bin/claude-policy-helper`

```bash
#!/bin/bash

# Get device posture
DEVICE_ID=$(system_profiler SPHardwareDataType | grep UUID | awk '{print $3}')
OS_VERSION=$(sw_vers -productVersion)
DEVICE_MANAGEMENT=$(mdmclient queries -raw | grep Enrolled)

# Fetch policy from server
POLICY=$(curl -s https://policy.example.com/api/v1/device/$DEVICE_ID \
  -H "Authorization: Bearer $(security find-generic-password -s 'policy-server' -a 'claude' -w)")

# Check if device compliant
if [ -z "$DEVICE_MANAGEMENT" ]; then
  # Device not managed — restrict capabilities
  POLICY=$(echo $POLICY | jq '.restrictedMode = true')
fi

# Return JSON wrapped in managedSettings key
echo "{\"managedSettings\": $POLICY}"
```

### Policy Server Response

```json
{
  "forceLoginOrgUUID": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "requiredMinimumVersion": "2.1.150",
  "permissions": {
    "deny": [
      "Read(./.env*)",
      "Read(./secrets/**)"
    ]
  },
  "sandbox": {
    "enabled": true
  },
  "restrictedMode": false
}
```

---

## Security Policies

### Policy 1: Baseline Security

**File**: `10-security-baseline.json`

```json
{
  "forceLoginMethod": "claudeai",
  "requiredMinimumVersion": "2.1.150",
  "permissions": {
    "deny": [
      "Read(./.env*)",
      "Read(./secrets/**)",
      "Bash(sudo *)",
      "Bash(curl * -o *)"
    ]
  },
  "sandbox": {
    "enabled": true,
    "filesystem": {
      "denyRead": ["~/.ssh", "~/.aws", "/etc/passwd"]
    }
  }
}
```

### Policy 2: Compliance (GDPR/HIPAA)

**File**: `20-compliance.json`

```json
{
  "claudeMd": "# Compliance Requirements\n\n- Never process PII without encryption\n- Log all data access\n- Comply with data retention policies\n- No PII in prompts or responses",
  "permissions": {
    "deny": [
      "WebFetch(domain:external.com)"
    ]
  },
  "skipWebFetchPreflight": false,
  "forceRemoteSettingsRefresh": true
}
```

### Policy 3: Development Team Restrictions

**File**: `30-dev-team.json`

```json
{
  "allowedMcpServers": [
    { "serverName": "github" },
    { "serverName": "qdrant" }
  ],
  "deniedMcpServers": [
    { "serverName": "filesystem" }
  ],
  "allowManagedMcpServersOnly": false,
  "strictPluginOnlyCustomization": ["skills", "hooks"],
  "enabledPlugins": {
    "code-formatter@official": true,
    "test-runner@team-tools": true
  }
}
```

### Policy 4: DevOps Team Permissions

**File**: `40-devops.json`

```json
{
  "permissions": {
    "allow": [
      "Bash(kubectl *)",
      "Bash(aws *)",
      "Bash(terraform *)",
      "Read(~/.kube/**)"
    ],
    "deny": [
      "Bash(kubectl delete)"
    ]
  },
  "env": {
    "AWS_PROFILE": "devops",
    "TERRAFORM_VERSION": "1.5.0"
  }
}
```

---

## Monitoring & Audit

### Collect Policy Information

Use `/status` endpoint to verify policies applied:

```bash
# Show active policy sources
/status

# Output example:
# Setting sources:
# - Enterprise managed settings (remote)
# - Project settings
# - User settings
```

### Verify Configuration

```bash
# Diagnose policy issues
/doctor

# Check for policy conflicts
/config
```

### Remote Configuration Refresh

Ensure fresh policy fetch at startup:

```json
{
  "forceRemoteSettingsRefresh": true
}
```

### Session Logging

Enable audit logging for compliance:

```bash
# Environment variable
export CLAUDE_CODE_SESSION_LOG=/var/log/claude-code/sessions.log

# Or in settings.json
{
  "env": {
    "CLAUDE_CODE_SESSION_LOG": "/var/log/claude-code/sessions.log"
  }
}
```

---

## Examples

### Example 1: Startup Company

**managed-settings.json**:

```json
{
  "requiredMinimumVersion": "2.1.150",
  "permissions": {
    "allow": ["Bash(npm run *)"],
    "deny": []
  },
  "sandbox": {
    "enabled": false
  }
}
```

*Rationale*: Trust developers, focus on productivity over restrictions.

### Example 2: Financial Services

**managed-settings.json**:

```json
{
  "forceLoginOrgUUID": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "forceLoginMethod": "claudeai",
  "requiredMinimumVersion": "2.1.150",
  "requiredMaximumVersion": "2.1.160",
  "permissions": {
    "deny": [
      "Read(./pii/**)",
      "Read(./secrets/**)",
      "Read(./.env*)",
      "WebFetch()"
    ]
  },
  "sandbox": {
    "enabled": true,
    "failIfUnavailable": true,
    "filesystem": {
      "denyRead": ["~/.ssh", "~/.aws", "/etc/passwd"]
    }
  },
  "skipWebFetchPreflight": false,
  "forceRemoteSettingsRefresh": true
}
```

*Rationale*: Strict compliance, no external network, version pinned, remote policy refresh.

### Example 3: Healthcare (HIPAA)

**managed-settings.json**:

```json
{
  "forceLoginOrgUUID": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "claudeMd": "# HIPAA Compliance\n\n- Never process patient data in prompts\n- All sessions logged and audited\n- No clipboard access\n- Encryption required for transit\n- Data retention: 90 days max",
  "permissions": {
    "deny": [
      "Read(./patient-data/**)",
      "Read(./.env*)",
      "WebFetch(domain:external.com)"
    ]
  },
  "sandbox": {
    "enabled": true,
    "filesystem": {
      "denyRead": ["~/.ssh", "~/.aws"]
    }
  },
  "forceRemoteSettingsRefresh": true
}
```

*Rationale*: HIPAA-compliant, audit logging required, strict data access.

### Example 4: Enterprise with Multi-Team Setup

**managed-settings.json**:

```json
{
  "forceLoginOrgUUID": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "requiredMinimumVersion": "2.1.150",
  "policyHelper": {
    "path": "/usr/local/bin/enterprise-policy-helper",
    "refreshIntervalMs": 3600000
  }
}
```

**managed-settings.d/10-security.json**:

```json
{
  "permissions": {
    "deny": [
      "Read(./.env*)",
      "Read(./secrets/**)",
      "Bash(sudo *)"
    ]
  },
  "sandbox": {
    "enabled": true
  }
}
```

**managed-settings.d/20-ml-team.json**:

```json
{
  "allowedMcpServers": [
    { "serverName": "github" },
    { "serverName": "qdrant" },
    { "serverName": "wandb" }
  ],
  "env": {
    "WANDB_API_KEY": "${WANDB_API_KEY}"
  }
}
```

*Rationale*: Dynamic policy via helper, baseline security + team-specific configs.

---

## Troubleshooting

### Policy Not Applied

**Check order:**
1. Run `/status` — see which policy sources loaded
2. Run `/doctor` — diagnose invalid entries
3. Check file permissions: `sudo ls -la /etc/claude-code/`
4. Verify JSON syntax: `jq < managed-settings.json`

### User Can Override Policy

**Verify precedence:**
- Managed always wins over user/project
- Check no higher-precedence source overrides
- Run `/status` to verify source order

### Policy Conflicts

**Diagnose:**
```bash
# View merged policy
/status

# Check drop-in files
ls -la /etc/claude-code/managed-settings.d/
```

**Resolve:**
- Check file names sorted correctly
- Verify no duplicate keys
- Merge order: base file first, then d/* alphabetically

---

## Deployment Checklist

Before deploying to production:

- [ ] Test locally on representative machines
- [ ] Verify all policy files valid JSON
- [ ] Check drop-in directory order (10-, 20-, etc.)
- [ ] Confirm organization UUID correct
- [ ] Test version requirements (min/max)
- [ ] Verify permissions don't block essential tools
- [ ] Test remote settings refresh (if enabled)
- [ ] Monitor first week for issues
- [ ] Document policy in runbook
- [ ] Train IT support team

---

## See Also

- [Claude Code Settings Reference](./claude-code-settings-reference.md)
- [Claude Code MCP Setup](./claude-code-mcp-setup.md)
- [Claude Code Plugins & Marketplaces](./claude-code-plugins-marketplaces.md)
- [Claude Code Advanced Configuration](./claude-code-advanced-config.md)
