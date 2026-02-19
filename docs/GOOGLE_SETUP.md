# Google OAuth Setup Guide

Orion ships with **no hardcoded Google credentials**. Each self-hosting user
must register their own Google Cloud OAuth application.

---

## Quick Start

### Option A — CLI Setup Wizard (recommended)

```
/google setup
```

The wizard walks you through creating a Google Cloud OAuth app and saves
your `client_id` to `~/.orion/google_oauth.json` (gitignored, permissions 0600).

### Option B — Environment Variables

```bash
export ORION_GOOGLE_CLIENT_ID="123456789-abc.apps.googleusercontent.com"
export ORION_GOOGLE_CLIENT_SECRET="GOCSPX-xxxxxxxx"   # optional for Desktop/PKCE
```

### Option C — API Endpoint (Web UI)

```
POST /api/google/configure
{
  "client_id": "123456789-abc.apps.googleusercontent.com",
  "client_secret": ""
}
```

---

## Step-by-Step: Create a Google Cloud OAuth App

1. **Go to** [Google Cloud Console → APIs & Services → Credentials](https://console.cloud.google.com/apis/credentials)

2. **Create a project** (or select an existing one)

3. **Enable the Generative Language API**
   - Navigate to *APIs & Services → Library*
   - Search for "Generative Language API" and enable it

4. **Configure the OAuth consent screen**
   - User type: *External* (or *Internal* for Workspace orgs)
   - App name: e.g. "Orion Agent"
   - Scopes: add `openid`, `email`, `profile`
   - Add yourself as a test user (if External + Testing status)

5. **Create OAuth 2.0 Client ID**
   - Click *Create Credentials → OAuth 2.0 Client ID*
   - Application type: **Desktop app** (recommended — enables PKCE, no client_secret needed)
   - Name: e.g. "Orion Desktop"
   - Click *Create*

6. **Copy the Client ID**
   - It looks like: `123456789012-abcdefghij.apps.googleusercontent.com`
   - The client_secret (e.g. `GOCSPX-...`) is optional for Desktop apps using PKCE

7. **Provide to Orion** via one of the three methods above

---

## Credential Resolution Order

Orion resolves Google OAuth credentials in this order (first non-empty wins):

| Priority | Source | Path / Variable |
|----------|--------|-----------------|
| 1 | Environment variable | `ORION_GOOGLE_CLIENT_ID` |
| 2 | Dedicated config file | `~/.orion/google_oauth.json` |
| 3 | Generic OAuth store | `~/.orion/oauth_clients.json` |

The same order applies for `ORION_GOOGLE_CLIENT_SECRET`.

---

## Security Model

- **No credentials ship with Orion** — `data/oauth_defaults.json` has empty placeholders
- **Config file permissions** — `~/.orion/google_oauth.json` is created with mode `0600` (owner-only)
- **Gitignored** — `.gitignore` covers `.env`, `credentials.json`, `secrets.json`
- **Scopes are restricted** — Only LLM-related scopes are requested:
  - Allowed: `openid`, `email`, `profile`, `cloud-platform`, `generative-language.*`
  - Blocked: Drive, Gmail, Calendar, YouTube, Contacts, Photos
- **PKCE (S256)** — Authorization Code flow with Proof Key for Code Exchange
- **Tokens stored encrypted** — via `GoogleCredentialManager` + `SecureStore`
- **Container isolation** — Sandbox gets a read-only access token (no refresh token)

---

## Managing Credentials

### Check Status

```
# CLI
/google status

# API
GET /api/google/configure
GET /api/google/status
```

### Delete Credentials

```
# CLI — run /google setup and press Enter without typing anything
/google setup

# API
DELETE /api/google/configure

# Manual
rm ~/.orion/google_oauth.json
```

### Connect / Disconnect Account

```
# CLI
/google login
/google disconnect

# API
POST /api/google/connect
POST /api/google/disconnect
```

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| "client_id not configured" | Run `/google setup` or set `ORION_GOOGLE_CLIENT_ID` |
| "Invalid client_id format" | Must match `<number>-<alphanum>.apps.googleusercontent.com` |
| "Token exchange failed" | Ensure the Generative Language API is enabled in your project |
| "Blocked scopes detected" | Use a dedicated Google account with LLM-only permissions |
| "Could not reach API server" | Start the API: `uvicorn orion.api.server:app --port 8001` |

---

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/google/configure` | Save client_id / client_secret |
| `GET` | `/api/google/configure` | Check credential config status |
| `DELETE` | `/api/google/configure` | Delete local config file |
| `POST` | `/api/google/connect` | Start OAuth flow (returns auth_url) |
| `GET` | `/api/google/callback` | OAuth callback handler |
| `GET` | `/api/google/status` | Account connection status |
| `POST` | `/api/google/disconnect` | Revoke token + clear credentials |
| `POST` | `/api/google/refresh` | Force host-side token refresh |
