# 🤖 AI Magic Guide: Efficient Project Registration
This guide explains how an AI agent can efficiently register and share new programs via Tailscale Magic.

## 🚀 Quick Registration Workflow
To share a new project, follow these steps without modifying the core logic:

1. **Detect Project Details**:
   - **Path**: The absolute path to the project folder.
   - **Main Script**: Identify the startup file (e.g., `main.py`, `api.py`, `start-all.js`).
   - **Port**: Find the port defined in the code (e.g., in `api.py` or `.env`).

2. **Update `projects.json`**:
   Add a new entry to `D:\tailscale magic\projects.json`. Use the following schema:
   ```json
   "project:[PORT]": {
       "path": "[ABSOLUTE_PATH]",
       "port": [PORT],
       "publicPort": "443",
       "serve_path": "/[YOUR-PATH]",
       "name": "[DISPLAY_NAME]",
       "description": "[TAGLINE]",
       "command": "[STARTUP_COMMAND]",
       "icon_url": "/api/proxy_icon?port=[PORT]&path=[FAVICON_PATH]"
   }
   ```
   - **Note**: Ensure the `publicPort` is usually `443` for Tailscale Funnel.
   - **Note**: `serve_path` should be unique.

3. **Activation**:
   - If `Tailscale Magic` is already running, save the file. The monitor loop in `core.py` will pick up the new project within 15-30 seconds or upon next restart.
   - Alternatively, execute `Start Magic.bat` to force a reload.

## 💡 Pro-Tips for AI Agents
- **Port Conflicts**: Always check if the port is already used in `projects.json` or by the system.
- **Icon Discovery**: Look for `favicon.ico`, `logo.png`, or `vite.svg` to populate the `icon_url`.
- **Startup Command**: Prefer commands that work cross-platform (e.g., `python api.py` instead of `python.exe`).

## 🛠️ Efficient Execution
Always check `D:\tailscale magic\projects.json` first to see the current registry. Before adding, ensure you have the correct absolute path to avoid directory errors.
