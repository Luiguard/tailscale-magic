import sys
import os
import asyncio
import json
import psutil
import httpx
import uvicorn
import webview
import time
import threading
import webbrowser
import websockets
import re
import tkinter as tk
from tkinter import filedialog
from typing import Optional, Dict, Any
from fastapi import FastAPI, HTTPException, Request, WebSocket
from fastapi.responses import (
    FileResponse,
    RedirectResponse,
    Response,
    HTMLResponse,
    JSONResponse,
)
from fastapi.staticfiles import StaticFiles
from starlette.websockets import WebSocketState
from plyer import notification

# Local Modules
from core import core_system, DASHBOARD_PORT, PROJECTS_FILE, BASE_PATH, log_event
from tray_app import start_tray
from security import SecurityGuard

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize the client inside the async context
    global http_client
    http_client = httpx.AsyncClient(timeout=30.0, follow_redirects=False)
    yield
    # Clean up on shutdown
    await http_client.aclose()

app = FastAPI(title="Tailscale Magic Portal", lifespan=lifespan)
http_client: httpx.AsyncClient = None

# Security Guard - DDoS & Hacking Protection
_ban_file = os.path.join(BASE_PATH, "banned_ips.json")
security_guard = SecurityGuard(ban_file=_ban_file)

# Hop-by-hop headers to strip in proxy
HOP_BY_HOP = [
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
]


def get_resource_path(relative_path):
    """Robust asset path resolution."""
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        p = os.path.join(meipass, relative_path)
        if os.path.exists(p):
            return p
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), relative_path)
    if os.path.exists(p):
        return p
    return os.path.abspath(relative_path)


STATIC_PATH = get_resource_path("static")
if os.path.exists(STATIC_PATH):
    app.mount("/static", StaticFiles(directory=STATIC_PATH), name="static")


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    import traceback

    print(f"Global Error: {exc}")
    traceback.print_exc()
    return JSONResponse(
        status_code=500,
        content={
            "status": "error",
            "detail": str(exc),
            "traceback": traceback.format_exc(),
        },
    )


@app.middleware("http")
async def security_middleware(request: Request, call_next):
    """Multi-layer security: DDoS protection, rate limiting, attack detection."""
    client_ip = request.client.host if request.client else "0.0.0.0"
    path = request.url.path
    method = request.method
    headers = dict(request.headers)

    # Estimate body size from content-length header
    body_size = int(headers.get('content-length', 0))

    allowed, reason = security_guard.check_request(
        client_ip=client_ip,
        path=path,
        method=method,
        headers=headers,
        body_size=body_size,
    )

    if not allowed:
        log_event(f"[SECURITY] BLOCKED {client_ip} -> {path}: {reason}")
        return JSONResponse(
            status_code=429 if 'rate' in (reason or '').lower() or 'burst' in (reason or '').lower() else 403,
            content={"status": "blocked", "reason": reason},
            headers={
                "Retry-After": "60",
                "X-RateLimit-Limit": "120",
            },
        )

    response = await call_next(request)

    # Security headers
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Cross-Origin-Resource-Policy"] = "cross-origin"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["X-XSS-Protection"] = "1; mode=block"

    return response


# --- UI ENDPOINTS ---


@app.get("/", response_class=HTMLResponse)
async def get_dashboard():
    dashboard_path = os.path.join(STATIC_PATH, "portal.html")
    if not os.path.exists(dashboard_path):
        return "Portal HTML not found in static directory."
    return FileResponse(dashboard_path)


@app.get("/admin", response_class=HTMLResponse)
async def get_admin_dashboard():
    admin_path = os.path.join(STATIC_PATH, "index.html")
    if not os.path.exists(admin_path):
        return "Admin HTML not found in static directory."
    return FileResponse(admin_path)


@app.get("/api/check_dependencies")
def check_deps():
    def check(cmd):
        try:
            import subprocess

            subprocess.run(
                cmd,
                capture_output=True,
                shell=True,
                creationflags=0x08000000 if os.name == "nt" else 0,
            )
            return True
        except Exception:
            return False

    return {
        "tailscale": check(["tailscale", "--version"]),
        "node": check(["npm", "--version"]),
        "python": check(["python", "--version"]),
    }


@app.get("/api/browse_path")
def browse_path():
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    path = filedialog.askdirectory(title="Wähle dein Projektverzeichnis")
    root.destroy()
    if not path:
        return {"path": ""}

    path = os.path.normpath(path)
    res = core_system.detect_project_type(path)
    return {
        "path": path,
        "type": res.get("type", "Unknown"),
        "suggestedCommand": res.get("command", ""),
    }


@app.get("/api/status")
def get_status():
    status = core_system.ts.get_status()
    projects = core_system.load_projects()
    node_name = status.get("Self", {}).get("DNSName", "").rstrip(".")

    # Build system ports map
    system_ports = {}
    try:
        system_ports = core_system.get_system_used_ports()
        # Convert int keys to str for JSON
        system_ports = {str(k): v for k, v in list(system_ports.items())[:30]}
    except Exception:
        pass

    return {
        "nodeName": node_name,
        "isLoggedIn": bool(node_name),
        "ipv4": status.get("Self", {}).get("TailscaleIPs", [""])[0],
        "projectsCount": len(projects),
        "activeCount": sum(1 for p in projects.values() if p.get("pid")),
        "managedProjects": projects,
        "systemPorts": system_ports,
    }


@app.get("/api/projects")
def get_projects():
    return core_system.load_projects()


@app.get("/api/logs/{project_key}")
def get_project_logs(project_key: str):
    return list(core_system.pm.project_logs.get(project_key, []))


@app.get("/portal/services.json")
def get_portal_services():
    """Format projects for the Magic Nav bar."""
    status = core_system.ts.get_status()
    hostname = status.get("Self", {}).get("DNSName", "").rstrip(".")
    
    # Read custom legal domain if installed via Setup
    settings_path = os.path.join(BASE_PATH, "settings.json")
    if os.path.exists(settings_path):
        try:
            with open(settings_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                if cfg.get("legal_domain"):
                    hostname = cfg["legal_domain"].rstrip("/")
        except:
            pass

    projects = core_system.load_projects()
    services = []

    # Add Dashboard itself
    services.append({
        "name": "Magic Hub",
        "url": "/portal.html",
        "icon": "fa-house-chimney-window",
        "is_public": True,
    })

    for key, p in projects.items():
        s_path = (p.get("serve_path") or "").strip("/")
        pub_port = p.get("publicPort", "443")
        if s_path:
            if s_path == "mediclean":
                url = f"https://{hostname}"
            else:
                url = f"https://{hostname}:8443/{s_path}"
        else:
            url = f"https://{hostname}:8443/"

        services.append({
            "name": p.get("name", key),
            "url": url,
            "description": p.get("description", ""),
            "icon_url": p.get("icon_url"),
            "icon": "fa-cube",
            "is_public": pub_port != "tailnet",
        })

    return {"hostname": hostname, "services": services}


@app.post("/api/projects/add")
async def add_project(request: Request):
    data = await request.json()
    path = data.get("path")
    if not path or not os.path.isdir(path):
        return {"status": "error", "message": "Ungültiger Pfad"}

    key = os.path.basename(path)
    projects = core_system.load_projects()
    if key in projects:
        key = f"{key}_{int(time.time())}"

    ptype_info = core_system.detect_project_type(path)
    port = core_system.get_free_port()

    projects[key] = {
        "name": key,
        "path": path,
        "port": port,
        "publicPort": "443",
        "command": ptype_info["command"] or "python -m http.server $PORT",
        "type": ptype_info["type"],
        "active": False,
    }
    core_system.save_projects(projects)
    return {"status": "ok", "key": key, "port": port}


@app.get("/api/refresh_all_metadata")
async def refresh_all():
    projects = core_system.load_projects()
    for port in [p.get("port") for p in projects.values() if p.get("port")]:
        await core_system.fetch_metadata(port)
    return {"status": "ok"}


@app.get("/api/analytics")
def get_analytics():
    return core_system.analytics


# --- SECURITY API ---


@app.get("/api/security/stats")
def get_security_stats():
    """Dashboard: View current security stats."""
    return security_guard.get_stats()


@app.post("/api/security/unban_all")
def unban_all_ips():
    """Emergency: Unban all blocked IPs."""
    security_guard.unban_all()
    return {"status": "ok", "message": "All IP bans cleared"}


@app.post("/api/security/unban")
async def unban_ip(request: Request):
    """Unban a specific IP by hash prefix."""
    data = await request.json()
    prefix = data.get("hash_prefix", "")
    if not prefix:
        raise HTTPException(status_code=400, detail="hash_prefix required")
    success = security_guard.unban_ip(prefix)
    return {"status": "ok" if success else "not_found"}


# --- DOWNLOAD / INSTALLER ---


@app.get("/api/download/installer")
async def download_installer():
    """Serve the TailscaleMagic installer/exe for download."""
    # Check the dist folder for the built executable
    installer_paths = [
        os.path.join(BASE_PATH, "dist", "TailscaleMagic.exe"),
        os.path.join(BASE_PATH, "dist", "TailscaleMagicSetup.exe"),
        os.path.join(BASE_PATH, "TailscaleMagic.exe"),
    ]
    for p in installer_paths:
        if os.path.exists(p):
            filename = os.path.basename(p)
            return FileResponse(
                p,
                media_type="application/octet-stream",
                filename=filename,
                headers={"Content-Disposition": f'attachment; filename="{filename}"'},
            )

    raise HTTPException(
        status_code=404,
        detail="Installer nicht gefunden. Bitte erst erstellen mit: pyinstaller TailscaleMagic.spec",
    )


# --- MISSING ENDPOINTS FOR ADMIN DASHBOARD ---


@app.post("/api/add_existing")
async def add_existing(request: Request):
    """Bind an already-running local app to Tailscale funnel."""
    local_port = int(request.query_params.get("local_port", 0))
    public_port = request.query_params.get("public_port", "443")
    serve_path = request.query_params.get("serve_path", "")

    if not local_port or local_port < 1 or local_port > 65535:
        raise HTTPException(status_code=400, detail="Ungültiger Port")

    projects = core_system.load_projects()
    key = f"existing:{local_port}"

    projects[key] = {
        "port": local_port,
        "publicPort": public_port,
        "serve_path": serve_path,
        "path": None,
        "pid": None,
        "command": None,
    }
    core_system.save_projects(projects)

    # Setup funnel if no serve_path (direct funnel)
    if not serve_path:
        core_system.ts.run_serve(local_port, public_port)

    # Fetch metadata
    meta = await core_system.fetch_metadata(local_port)
    if meta:
        projects[key]["name"] = meta.get("title", key)
        projects[key]["description"] = meta.get("description", "Running on Magic Funnel")
        if meta.get("icon"):
            projects[key]["icon_url"] = f"/api/proxy_icon?port={local_port}&path=favicon.svg"
        core_system.save_projects(projects)

    return {"status": "ok", "key": key}


@app.post("/api/host_project")
async def host_project(request: Request):
    """Start a project from a directory and publish it."""
    path = request.query_params.get("path", "")
    command = request.query_params.get("command", "")
    public_port = request.query_params.get("public_port", "443")
    serve_path = request.query_params.get("serve_path", "")

    if not path or not os.path.isdir(path):
        raise HTTPException(status_code=400, detail="Ungültiger Pfad")

    if not command:
        detection = core_system.detect_project_type(path)
        command = detection.get("command", "")

    if not command:
        raise HTTPException(status_code=400, detail="Kein Startbefehl erkannt")

    port = core_system.get_free_port()
    if not port:
        raise HTTPException(status_code=500, detail="Kein freier Port gefunden")

    folder_name = os.path.basename(path)
    key = f"project:{port}"

    projects = core_system.load_projects()
    projects[key] = {
        "path": path,
        "port": port,
        "publicPort": public_port,
        "serve_path": serve_path,
        "command": command,
    }

    proc = core_system.pm.start_project(key, path, port, command)
    if proc:
        projects[key]["pid"] = proc.pid

    # Setup funnel if no serve_path
    if not serve_path:
        core_system.ts.run_serve(port, public_port)

    core_system.save_projects(projects)

    # Fetch metadata after a short delay
    import asyncio
    await asyncio.sleep(3)
    meta = await core_system.fetch_metadata(port)
    if meta:
        projects[key]["name"] = meta.get("title", folder_name)
        projects[key]["description"] = meta.get("description", "")
        core_system.save_projects(projects)

    return {"status": "ok", "key": key, "port": port}


@app.post("/api/reset_all")
async def reset_all():
    """Stop all services and reset Tailscale."""
    projects = core_system.load_projects()
    for key, p in list(projects.items()):
        core_system.pm.stop_project(key)
        port = p.get("port")
        if port:
            core_system.pm.kill_port(port)

    core_system.ts.cleanup_all()
    core_system.save_projects({})
    return {"status": "ok"}


@app.delete("/api/serve")
async def remove_service(request: Request):
    """Stop and remove a single service."""
    key = request.query_params.get("path", "")
    if not key:
        raise HTTPException(status_code=400, detail="Kein Projektschlüssel angegeben")

    projects = core_system.load_projects()
    if key not in projects:
        raise HTTPException(status_code=404, detail="Projekt nicht gefunden")

    p = projects[key]
    port = p.get("port")
    pub_port = str(p.get("publicPort", "443"))
    s_path = p.get("serve_path", "")

    # Stop process
    core_system.pm.stop_project(key)
    if port:
        core_system.pm.kill_port(port)

    # Stop funnel if direct (no serve_path)
    if port and not s_path:
        core_system.ts.stop_serve(port, pub_port)

    del projects[key]
    core_system.save_projects(projects)
    return {"status": "ok"}


@app.post("/api/update_project_port")
async def update_project_port(request: Request):
    """Change the local port of a project and restart it."""
    key = request.query_params.get("key", "")
    new_port = int(request.query_params.get("new_port", 0))

    if not key or not new_port:
        raise HTTPException(status_code=400, detail="Key und Port müssen angegeben werden")

    projects = core_system.load_projects()
    if key not in projects:
        raise HTTPException(status_code=404, detail="Projekt nicht gefunden")

    p = projects[key]
    old_port = p.get("port")

    # Stop old process
    core_system.pm.stop_project(key)
    if old_port:
        core_system.pm.kill_port(old_port)

    # Update port
    p["port"] = new_port

    # Restart if we have a command
    cmd = p.get("command")
    path = p.get("path")
    if cmd and path:
        proc = core_system.pm.start_project(key, path, new_port, cmd)
        if proc:
            p["pid"] = proc.pid

    core_system.save_projects(projects)
    return {"status": "ok", "new_port": new_port}


@app.get("/api/fetch_metadata")
async def api_fetch_metadata(port: int, save: bool = False):
    """Fetch metadata from a running service."""
    meta = await core_system.fetch_metadata(port, force=True)
    if not meta:
        return {"status": "error", "message": "Metadata nicht abrufbar"}

    if save:
        projects = core_system.load_projects()
        for key, p in projects.items():
            if p.get("port") == port:
                p["name"] = meta.get("title", p.get("name", key))
                p["description"] = meta.get("description", "")
                if meta.get("icon"):
                    p["icon_url"] = f"/api/proxy_icon?port={port}&path=favicon.svg"
                core_system.save_projects(projects)
                break

    return {"status": "success", **meta}


@app.get("/api/browse")
def api_browse():
    """Browse for a folder (alias for /api/browse_path)."""
    return browse_path()


@app.get("/api/logs")
def api_logs_query(request: Request):
    """Get logs for a project via query parameter."""
    key = request.query_params.get("path", "")
    if not key:
        return []
    return list(core_system.pm.project_logs.get(key, []))


@app.get("/api/proxy_icon")
async def proxy_icon(port: int, path: str = "favicon.ico"):
    """Proxy a favicon/icon from a local service."""
    url = f"http://127.0.0.1:{port}/{path.lstrip('/')}"
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            res = await client.get(url, follow_redirects=True)
            if res.status_code == 200:
                content_type = res.headers.get("content-type", "image/x-icon")
                return Response(content=res.content, media_type=content_type)
    except Exception:
        pass
    raise HTTPException(status_code=404, detail="Icon not found")


# --- LOGIC & PROXY ---


async def _do_proxy(
    target: str, request: Request, port: int, project_key: Optional[str] = None
):
    """Core HTTP Proxy Logic."""
    body = await request.body()
    headers = dict(request.headers)
    headers = {
        k: v for k, v in headers.items() if k.lower() not in HOP_BY_HOP
    }

    try:
        resp = await http_client.request(
            method=request.method, url=target, headers=headers, content=body
        )
        resp_headers: Dict[str, Any] = {}
        for k, v in resp.headers.items():
            kl = k.lower()
            if kl not in HOP_BY_HOP and kl not in [
                "content-encoding",
                "content-security-policy",
            ]:
                resp_headers[k] = v

        content = resp.content
        if "html" in resp_headers.get("content-type", "").lower():
            html = content.decode("utf-8", errors="ignore")
            # Skip injection for portal.html (already has magic-nav embedded)
            if "magic-nav.js" not in html:
                # Injected Assets for Portal Bar
                fa_link = '<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">'
                css_link = '<link rel="stylesheet" href="/static/magic-nav.css">'
                js_link = '<script src="/static/magic-nav.js" defer></script>'
                injection = f"{fa_link}{css_link}{js_link}"

                if "</body>" in html:
                    html = html.replace("</body>", f"{injection}</body>")
                else:
                    html = html + injection

            content = html.encode("utf-8")
            resp_headers["content-length"] = str(len(content))

        # Analytics Tracking
        if project_key:
            visitor_ip = request.client.host if request.client else "Unknown"
            core_system.record_hit(project_key, visitor_ip, len(content))

        return Response(
            content=content, status_code=resp.status_code, headers=resp_headers
        )
    except Exception as e:
        print(f"Proxy Error {target}: {e}")
        return Response(
            content=f"Dienst auf Port {port} antwortet nicht.".encode(),
            status_code=502,
        )


class WebSocketProxyMiddleware:
    """ASGI Middleware that intercepts WebSocket upgrade requests and proxies
    them to the correct backend via raw TCP. This bypasses FastAPI/Starlette's
    WebSocket handling entirely, which is necessary because Vite's Node.js
    WebSocket server only processes upgrades via the Node.js HTTP 'upgrade' event.
    Python WebSocket client libraries (websockets, aiohttp) cannot handshake with it.
    """
    
    def __init__(self, app):
        self.app = app
    
    async def __call__(self, scope, receive, send):
        if scope["type"] != "websocket":
            await self.app(scope, receive, send)
            return
        
        # Determine target port from the path
        path = scope.get("path", "/").strip("/")
        query_string = scope.get("query_string", b"").decode()
        projects = core_system.load_projects()
        
        target_port = None
        sorted_projects = sorted(
            projects.items(),
            key=lambda x: len((x[1].get("serve_path") or "").strip("/")),
            reverse=True
        )
        
        for key, p in sorted_projects:
            s_path = (p.get("serve_path") or "").strip("/")
            if s_path and (path == s_path or path.startswith(s_path + "/")):
                target_port = p["port"]
                break
        
        if not target_port:
            # Fallback to root project
            for key, p in projects.items():
                if not (p.get("serve_path") or "").strip("/"):
                    target_port = p["port"]
                    break
        
        if not target_port:
            # No target found, let FastAPI handle it (will return 404)
            await self.app(scope, receive, send)
            return
        
        log_event(f"[WS_MIDDLEWARE] Proxying /{path} -> port {target_port}")
        
        # Build the target URL path
        target_path = f"/{path}"
        if query_string:
            target_path += f"?{query_string}"
        
        # Reconstruct the original HTTP headers from the ASGI scope
        headers_dict = {}
        for name, value in scope.get("headers", []):
            headers_dict[name.decode().lower()] = value.decode()
        
        try:
            # Open raw TCP connection to target
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection("127.0.0.1", target_port),
                timeout=10.0
            )
            
            # Build the HTTP Upgrade request with ALL original headers
            import base64
            ws_key = headers_dict.get("sec-websocket-key", base64.b64encode(os.urandom(16)).decode())
            ws_version = headers_dict.get("sec-websocket-version", "13")
            ws_extensions = headers_dict.get("sec-websocket-extensions", "")
            ws_protocol = headers_dict.get("sec-websocket-protocol", "")
            
            upgrade_lines = [
                f"GET {target_path} HTTP/1.1",
                f"Host: localhost:{target_port}",
                "Connection: Upgrade",
                "Upgrade: websocket",
                f"Sec-WebSocket-Key: {ws_key}",
                f"Sec-WebSocket-Version: {ws_version}",
                f"Origin: http://localhost:{target_port}",
                "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            ]
            if ws_extensions:
                upgrade_lines.append(f"Sec-WebSocket-Extensions: {ws_extensions}")
            if ws_protocol:
                upgrade_lines.append(f"Sec-WebSocket-Protocol: {ws_protocol}")
            
            upgrade_request = "\r\n".join(upgrade_lines) + "\r\n\r\n"
            
            writer.write(upgrade_request.encode())
            await writer.drain()
            
            # Read the upgrade response from Vite
            response_data = b""
            try:
                while b"\r\n\r\n" not in response_data:
                    chunk = await asyncio.wait_for(reader.read(4096), timeout=10.0)
                    if not chunk:
                        log_event(f"[WS_ERR] Connection closed during upgrade")
                        writer.close()
                        # Send a WebSocket close to the client
                        await send({"type": "websocket.close", "code": 1011})
                        return
                    response_data += chunk
            except asyncio.TimeoutError:
                log_event(f"[WS_ERR] Timeout waiting for upgrade response from port {target_port}")
                writer.close()
                await send({"type": "websocket.close", "code": 1011})
                return
            
            response_line = response_data.split(b"\r\n")[0].decode()
            log_event(f"[WS_UPGRADE] Backend response: {response_line}")
            
            if b"101" not in response_data.split(b"\r\n")[0]:
                log_event(f"[WS_ERR] Upgrade rejected: {response_line}")
                writer.close()
                await send({"type": "websocket.close", "code": 1011})
                return
            
            # Extract response headers for the client
            response_headers = []
            for line in response_data.split(b"\r\n")[1:]:
                if line == b"":
                    break
                if b": " in line:
                    h_name, h_value = line.split(b": ", 1)
                    response_headers.append([h_name.lower(), h_value])
            
            # Accept the WebSocket on the client side
            await send({
                "type": "websocket.accept",
                "headers": response_headers,
            })
            
            log_event(f"[WS_OK] WebSocket proxy established for /{path}")
            
            # Any leftover data after the HTTP response headers
            leftover = response_data.split(b"\r\n\r\n", 1)[1] if b"\r\n\r\n" in response_data else b""
            
            # Bidirectional relay
            relay_active = True
            
            async def relay_backend_to_client():
                """Read raw WS frames from Vite (unmasked), forward as ASGI messages."""
                nonlocal relay_active
                try:
                    buf = leftover
                    while relay_active:
                        if len(buf) < 2:
                            data = await reader.read(8192)
                            if not data:
                                break
                            buf += data
                            continue
                        
                        b1, b2 = buf[0], buf[1]
                        opcode = b1 & 0x0F
                        is_masked = (b2 & 0x80) != 0
                        plen = b2 & 0x7F
                        hdr = 2
                        
                        if plen == 126:
                            while len(buf) < 4:
                                d = await reader.read(8192)
                                if not d: return
                                buf += d
                            plen = int.from_bytes(buf[2:4], "big")
                            hdr = 4
                        elif plen == 127:
                            while len(buf) < 10:
                                d = await reader.read(8192)
                                if not d: return
                                buf += d
                            plen = int.from_bytes(buf[2:10], "big")
                            hdr = 10
                        
                        if is_masked:
                            hdr += 4
                        
                        total = hdr + plen
                        while len(buf) < total:
                            d = await reader.read(8192)
                            if not d: return
                            buf += d
                        
                        payload = buf[hdr:total]
                        if is_masked:
                            mk = buf[hdr-4:hdr]
                            payload = bytes(b ^ mk[i%4] for i, b in enumerate(payload))
                        buf = buf[total:]
                        
                        if opcode == 0x1:  # Text
                            await send({"type": "websocket.send", "text": payload.decode("utf-8", errors="replace")})
                        elif opcode == 0x2:  # Binary
                            await send({"type": "websocket.send", "bytes": payload})
                        elif opcode == 0x8:  # Close
                            relay_active = False
                            break
                        elif opcode == 0x9:  # Ping -> Pong
                            pong = _build_ws_frame(payload, opcode=0xA, mask=True)
                            writer.write(pong)
                            await writer.drain()
                except Exception as e:
                    log_event(f"[WS_B2C_END] {e}")
                    relay_active = False
            
            async def relay_client_to_backend():
                """Read ASGI WebSocket messages from client, send as masked WS frames to Vite."""
                nonlocal relay_active
                try:
                    while relay_active:
                        message = await receive()
                        if message["type"] == "websocket.receive":
                            data = message.get("text", "")
                            if data:
                                frame = _build_ws_frame(data.encode("utf-8"), opcode=0x1, mask=True)
                            else:
                                frame = _build_ws_frame(message.get("bytes", b""), opcode=0x2, mask=True)
                            writer.write(frame)
                            await writer.drain()
                        elif message["type"] == "websocket.disconnect":
                            relay_active = False
                            break
                except Exception as e:
                    log_event(f"[WS_C2B_END] {e}")
                    relay_active = False
            
            done, pending = await asyncio.wait(
                [asyncio.create_task(relay_backend_to_client()),
                 asyncio.create_task(relay_client_to_backend())],
                return_when=asyncio.FIRST_COMPLETED,
            )
            for t in pending:
                t.cancel()
            
            writer.close()
            
        except Exception as e:
            log_event(f"[WS_MIDDLEWARE_ERR] {e}")
            try:
                await send({"type": "websocket.close", "code": 1011})
            except Exception:
                pass


def _build_ws_frame(payload: bytes, opcode: int = 0x1, mask: bool = True) -> bytes:
    """Build a WebSocket frame. Client->Server frames must be masked."""
    frame = bytearray()
    frame.append(0x80 | opcode)  # FIN + opcode
    
    length = len(payload)
    if mask:
        if length < 126:
            frame.append(0x80 | length)
        elif length < 65536:
            frame.append(0x80 | 126)
            frame.extend(length.to_bytes(2, "big"))
        else:
            frame.append(0x80 | 127)
            frame.extend(length.to_bytes(8, "big"))
        
        mask_key = os.urandom(4)
        frame.extend(mask_key)
        frame.extend(bytes(b ^ mask_key[i % 4] for i, b in enumerate(payload)))
    else:
        if length < 126:
            frame.append(length)
        elif length < 65536:
            frame.append(126)
            frame.extend(length.to_bytes(2, "big"))
        else:
            frame.append(127)
            frame.extend(length.to_bytes(8, "big"))
        frame.extend(payload)
    
    return bytes(frame)


# Mount the WebSocket proxy middleware
app.add_middleware(WebSocketProxyMiddleware)


@app.api_route("/{proxy_path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def catch_all(proxy_path: str, request: Request):
    """Dynamic path-based proxy / Static Dashboard."""
    # Internal routes should never be proxied
    if proxy_path.startswith("api/") or proxy_path.startswith("portal/"):
        return None

    # Log incoming proxy requests for debugging
    log_event(f"[PROXY_REQ] {request.method} {proxy_path} q={request.url.query}")

    # Check Local Static Files
    p_path = str(proxy_path)
    clean_path = p_path
    if p_path.startswith("static/"):
        # Use explicit string manipulation to aid static analysis
        clean_path = p_path.replace("static/", "", 1)
    static_file = os.path.join(STATIC_PATH, clean_path)
    if os.path.isfile(static_file) and proxy_path:
        return FileResponse(static_file)

    projects = core_system.load_projects()
    # Sort by serve_path length descending to ensure longest match (e.g. /schule/api) wins over /schule
    sorted_projects = sorted(
        projects.items(),
        key=lambda x: len((x[1].get("serve_path") or "").strip("/")),
        reverse=True
    )

    # Path-based proxy
    for key, p in sorted_projects:
        s_path = (p.get("serve_path") or "").strip("/")
        if s_path:
            # Check for exact root match without trailing slash
            if proxy_path == s_path:
                return RedirectResponse(url=f"/{s_path}/", status_code=307)
                
            if proxy_path.startswith(s_path + "/"):
                query = f"?{request.url.query}" if request.url.query else ""
                target_url = f"http://127.0.0.1:{p['port']}/{proxy_path}{query}"
                return await _do_proxy(target_url, request, p["port"], key)

    # Root proxy fallback
    for key, p in projects.items():
        if not (p.get("serve_path") or "").strip("/"):
            query = f"?{request.url.query}" if request.url.query else ""
            target_url = f"http://127.0.0.1:{p['port']}/{proxy_path}{query}"
            return await _do_proxy(target_url, request, p["port"], key)

    # Default UI
    if request.method == "GET" and "." not in proxy_path:
        return FileResponse(os.path.join(STATIC_PATH, "portal.html"))

    raise HTTPException(status_code=404)


# --- APP BOOT ---


def on_exit():
    os._exit(0)

dashboard_window = None

def show_window():
    if dashboard_window:
        dashboard_window.show()

def run_uvicorn():
    uvicorn.run(app, host="127.0.0.1", port=DASHBOARD_PORT, log_level="error")

if __name__ == "__main__":
    threading.Thread(target=core_system.startup_sequence, daemon=True).start()
    threading.Thread(target=core_system.monitor_loop, daemon=True).start()

    print(f"Magic Portal starting on port {DASHBOARD_PORT}...")

    # Run Server in background
    threading.Thread(target=run_uvicorn, daemon=True).start()

    # Start Tray in separate thread
    threading.Thread(
        target=lambda: start_tray(show_window, on_exit), daemon=True
    ).start()

    # Setup Native App Window
    dashboard_window = webview.create_window(
        title="Magic Funnel Control Center",
        url=f"http://127.0.0.1:{DASHBOARD_PORT}/admin",
        width=1280,
        height=800,
        hidden=True, # Start hidden, opened via Tray
        frameless=False,
    )

    # Main thread must run the GUI loop
    webview.start(private_mode=False)
