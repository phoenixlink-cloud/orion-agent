# Troubleshooting

Common issues and solutions for Orion Agent.

## Installation Issues

### "pip: command not found"

Python's pip may not be in your PATH:
```bash
python -m pip install orion-agent
```

### "No matching distribution found for orion-agent"

Ensure you have Python 3.10+:
```bash
python --version
```

If you have an older version, upgrade Python first.

### Build errors on Windows

Some dependencies require C++ build tools:
```powershell
winget install Microsoft.VisualStudio.2022.BuildTools
```

### "Permission denied" during install

Use a virtual environment:
```bash
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install orion-agent
```

## Connection Issues

### "No API key found"

Set your API key as an environment variable:
```bash
# Linux/macOS
export OPENAI_API_KEY="sk-your-key"

# Windows PowerShell
$env:OPENAI_API_KEY="sk-your-key"
```

Or configure within Orion:
```
> /settings key openai sk-your-key
```

### "Failed to connect to Orion API" (Web UI)

1. Ensure the API server is running:
```bash
uvicorn orion.api.server:app --port 8001
```

2. Check the port matches in `.env.local`:
```
NEXT_PUBLIC_API_URL=http://localhost:8001
NEXT_PUBLIC_WS_URL=ws://localhost:8001/ws/chat
```

3. Restart the Web UI after changing `.env.local`:
```bash
cd orion-web
npm run dev
```

### "Connection refused" to Ollama

Ensure Ollama is running:
```bash
ollama serve
```

Check the URL configuration:
```
> /settings ollama_url http://localhost:11434
```

### API key rejected by provider

- Verify the key is correct (no extra spaces)
- Check that the key has the required permissions
- Ensure your account has available credits/quota

## Workspace Issues

### "Workspace not set"

Set a workspace before requesting code operations:
```
> /workspace /path/to/your/project
```

### "Path is not a directory"

The workspace path must point to an existing directory:
```bash
# Check the path exists
ls /path/to/your/project
```

### "Operation blocked by AEGIS: path escape"

You're trying to access a file outside the workspace. Orion cannot:
- Read files outside the workspace
- Follow symlinks that point outside the workspace
- Use `../` to escape the workspace

**Solution:** Set the workspace to a parent directory that contains all needed files, or work on files within the current workspace.

## Mode Issues

### "Operation not permitted in safe mode"

Switch to a mode that allows the operation:
```
> /mode pro       # For file editing
> /mode project   # For command execution
```

### "Command execution not allowed"

Command execution is only available in `project` mode:
```
> /mode project
```

And the command must be in the allowlist.

## LLM Issues

### Slow responses

- Check your internet connection
- Try a faster model (e.g., GPT-3.5-turbo instead of GPT-4)
- Use local Ollama for zero-latency routing
- Reduce `max_tokens` in settings

### "Rate limit exceeded"

- Wait a moment and retry
- Upgrade your API plan for higher limits
- Switch to a different provider temporarily

### "Model not found"

Verify the model name is correct:
```
> /settings model gpt-4o
```

For Ollama, ensure the model is pulled:
```bash
ollama pull llama3
```

### Garbled or incorrect output

- Try lowering the temperature:
```
> /settings temperature 0.2
```
- Try a different model
- Provide more context in your request

## Memory Issues

### Memory not persisting

- Check that the workspace has write permissions
- Verify `.orion/` directory exists in the workspace
- Check disk space

### Institutional memory growing too large

Clear old patterns:
```
> /memory clear institutional
```

Or adjust retention settings in `~/.orion/config.yaml`:
```yaml
memory:
  tier2_retention_days: 14  # Reduce from default 30
```

## Web UI Issues

### Web UI shows "Not connected"

1. Check API server is running on the correct port
2. Check browser console for CORS errors
3. Verify `.env.local` port matches the API server port

### WebSocket disconnects frequently

- Check for proxy/firewall interference
- If behind nginx, increase `proxy_read_timeout`
- Check API server logs for errors

### Web UI not loading

1. Check Node.js is installed (v18+)
2. Install dependencies: `npm install`
3. Check for port conflicts: `netstat -an | findstr 3001`

## Docker Issues

### Container won't start

Check logs:
```bash
docker logs orion-api
```

Common causes:
- Missing environment variables
- Port already in use
- Volume permission issues

### "Port already in use"

Find and stop the process using the port:
```bash
# Linux/macOS
lsof -i :8001
kill <PID>

# Windows
netstat -ano | findstr :8001
taskkill /PID <PID> /F
```

## Diagnostic Commands

### /doctor

Runs 15 diagnostic checks:
```
> /doctor
```

Reports: Python version, Git, workspace, LLM provider, API keys, memory engine, Docker, and more.

### /health

Checks integration health:
```
> /health
```

Reports: Provider connectivity, latency, API key validity.

## Log Locations

| Log | Location |
|-----|----------|
| Main log | `~/.orion/logs/orion.log` |
| AEGIS log | `~/.orion/logs/aegis.log` |
| API server | stdout (or configured file) |

### Enable debug logging

```bash
export ORION_LOG_LEVEL=DEBUG
```

Or in config:
```yaml
logging:
  level: DEBUG
```

## Getting Help

If your issue isn't listed here:

1. Check the [FAQ](FAQ.md)
2. Search [GitHub Issues](https://github.com/phoenixlink-cloud/orion-agent/issues)
3. Open a new issue with:
   - Orion version (`orion --version`)
   - OS and Python version
   - Steps to reproduce
   - Error messages and logs
4. Contact support@phoenixlink.co.za

---

**Next:** [FAQ](FAQ.md) | [Installation](INSTALLATION.md)
