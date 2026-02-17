# Orion Web UI

Web interface for Orion - Governed AI Assistant.

## Quick Start

### 1. Start the Orion API Server (Required)

```bash
# From the orion-agent root
pip install -e ".[dev]"

# Start the API server
uvicorn orion.api.server:app --reload --port 8001
```

### 2. Start the Web UI

```bash
# From the orion-web directory
cd orion-web

# Install dependencies (first time only)
npm install

# Run development server
npm run dev
```

### 3. Open in Browser

- **Web UI**: http://localhost:3000
- **API Server**: http://localhost:8001 (health check: http://localhost:8001/health)

## Full Stack Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Orion Web UI                            │
│                   (Next.js @ :3001)                         │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐        │
│  │  Home   │  │  Chat   │  │Settings │  │  Aegis  │        │
│  └────┬────┘  └────┬────┘  └────┬────┘  └────┬────┘        │
└───────┼────────────┼────────────┼────────────┼──────────────┘
        │            │            │            │
        └────────────┴─────┬──────┴────────────┘
                           │
                    ┌──────▼──────┐
                    │  API Client │
                    │ (lib/api.ts)│
                    └──────┬──────┘
                           │ HTTP
                    ┌──────▼──────┐
                    │ Orion API   │
                    │ (FastAPI)   │
                    │   @ :8001   │
                    └──────┬──────┘
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
┌───────▼───────┐  ┌───────▼───────┐  ┌───────▼───────┐
│  SecureStore  │  │   config.py   │  │ settings.json │
│ (API Keys)    │  │  (Defaults)   │  │ (User Prefs)  │
└───────────────┘  └───────────────┘  └───────────────┘
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/api/keys/status` | GET | Get API key status |
| `/api/keys/set` | POST | Set an API key |
| `/api/keys/{provider}` | DELETE | Remove an API key |
| `/api/models/mode` | GET | Get model mode (local/cloud) |
| `/api/models/mode` | POST | Set model mode |
| `/api/settings` | GET | Get all settings |
| `/api/settings` | POST | Update settings |
| `/api/ollama/status` | GET | Check Ollama availability |

## Structure

```
orion-web/
├── src/
│   ├── app/
│   │   ├── layout.tsx      # Root layout with fonts
│   │   ├── page.tsx        # Home page (Hero)
│   │   └── settings/
│   │       └── page.tsx    # Settings page
│   ├── components/
│   │   ├── Shell.tsx       # Page wrapper
│   │   ├── Hero.tsx        # Landing hero section
│   │   ├── BrandBlock.tsx  # Logo + tagline
│   │   ├── Button.tsx      # Primary/secondary buttons
│   │   ├── StatusRow.tsx   # Status indicators
│   │   └── SettingsPanel.tsx # Feature toggles + commands
│   ├── visuals/
│   │   ├── AegisGridBackdrop.tsx  # Grid + arcs background
│   │   ├── OrionCore.tsx          # Central orb
│   │   └── Constellation.tsx      # Node lines
│   └── design/
│       └── tokens.css      # Design tokens (colors, spacing, motion)
├── design/
│   └── tokens.json         # Source of truth for tokens
├── package.json
└── tsconfig.json
```

## Design System

### Layers
1. **Aegis Layer** (Background): Grid + arcs + starfield
2. **Orion Layer** (Presence): Central orb + constellation
3. **UI Layer** (Interaction): Logo, CTAs, status

### Tokens
All styling comes from CSS variables defined in `tokens.css`:
- Colors: `--bg0`, `--bg1`, `--glow`, `--text`, `--muted`, `--line`, `--grid`
- Radius: `--r-sm`, `--r-md`, `--r-lg`
- Spacing: `--space-1` through `--space-8`
- Motion: `--ease`, `--slow`, `--pulse`

### Rules
- No hardcoded colors or spacing
- Everything uses design tokens
- Motion is slow and calm (no blinking/bouncing)
- Max content width: 1120px

## Pages

### Home (`/`)
Landing page with:
- Brand block (ORION + tagline)
- Orion core visualization
- Call-to-action buttons
- Status row

### Settings (`/settings`)
Configuration page with:
- Feature toggles (streaming, web access, image gen, etc.)
- Command reference
- Mode selection

## Integration with CLI

The web UI is designed to work alongside the Orion CLI:
1. User runs CLI or desktop app
2. CLI can launch web UI on localhost
3. Web UI provides visual settings and status
4. CLI handles actual AI operations

## Development

```bash
# Run with hot reload
npm run dev

# Type check
npx tsc --noEmit

# Lint
npm run lint
```
