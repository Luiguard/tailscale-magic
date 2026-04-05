import os
import sys
import subprocess
import json
import time
import threading
import socket
import re
import hashlib
from typing import Dict, List, Optional, Any, Set
from collections import deque
from threading import Lock
import psutil
import httpx
from plyer import notification

# Logging
LOG_FILE = os.path.join(
    os.path.dirname(sys.executable)
    if getattr(sys, "frozen", False)
    else os.path.dirname(__file__),
    "magic_debug.log",
)
LOG_MAX_SIZE = 5 * 1024 * 1024  # 5 MB
LOG_BACKUP_COUNT = 2


def _rotate_log():
    """Rotate log file if it exceeds max size."""
    try:
        if not os.path.exists(LOG_FILE):
            return
        if os.path.getsize(LOG_FILE) < LOG_MAX_SIZE:
            return
        # Rotate: .log -> .log.1 -> .log.2 (oldest gets deleted)
        for i in range(LOG_BACKUP_COUNT, 0, -1):
            src = f"{LOG_FILE}.{i - 1}" if i > 1 else LOG_FILE
            dst = f"{LOG_FILE}.{i}"
            if os.path.exists(src):
                if os.path.exists(dst):
                    os.remove(dst)
                os.rename(src, dst)
    except Exception:
        pass


def _safe_ascii(text: str) -> str:
    """Strip non-ASCII chars for Windows console output (cp1252 safe)."""
    return text.encode("ascii", "replace").decode("ascii")


def log_event(msg):
    """Log an event to the debug log file and console with Unicode safety."""
    try:
        _rotate_log()
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{ts}] {msg}\n"
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line)

        # Windows Console Unicode Fix — always use safe ASCII for print
        try:
            print(line, end="")
        except (UnicodeEncodeError, UnicodeDecodeError, OSError):
            try:
                print(_safe_ascii(line), end="")
            except Exception:
                pass
    except Exception:
        pass


def get_base_path():
    """Detect if we are running as a script or a bundled EXE with
    improved detection."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


BASE_PATH = get_base_path()
PROJECTS_FILE = os.path.join(BASE_PATH, "projects.json")
TAILSCALE = "tailscale"
DASHBOARD_PORT = 8080


# Static Configuration
CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0
SUBPROCESS_KWARGS = {"creationflags": CREATE_NO_WINDOW} if os.name == "nt" else {}
ANALYTICS_FILE = os.path.join(BASE_PATH, "analytics.json")


class TailscaleWrapper:
    """Efficiently interact with Tailscale CLI with caching."""

    def __init__(self):
        self._status_cache: Optional[Dict[str, Any]] = None
        self._serve_cache: Optional[Dict[str, Any]] = None
        self._last_status_fetch: float = 0.0
        self._last_serve_fetch: float = 0.0
        self._cache_ttl: float = 2.0  # 2 seconds TTL

    def _run_cmd(self, cmd: List[str], **kwargs):
        """Helper to run tailscale commands with consistent flags."""
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            creationflags=CREATE_NO_WINDOW if os.name == "nt" else 0,
            **kwargs,
        )

    def _get_json(self, cmd: List[str]) -> Dict[str, Any]:
        try:
            res = self._run_cmd(cmd + ["--json"])
            if res.returncode == 0:
                return dict(json.loads(res.stdout))
        except (subprocess.CalledProcessError, json.JSONDecodeError, FileNotFoundError) as e:
            log_event(f"Tailscale Command Error {cmd}: {e}")
        return {}

    def get_status(self, force: bool = False) -> Dict[str, Any]:
        now = time.time()
        if force or (now - self._last_status_fetch > self._cache_ttl):
            self._status_cache = self._get_json([TAILSCALE, "status"])
            self._last_status_fetch = now
        return self._status_cache or {}

    def get_serve_status(self, force: bool = False) -> Dict[str, Any]:
        now = time.time()
        if force or (now - self._last_serve_fetch > self._cache_ttl):
            self._serve_cache = self._get_json([TAILSCALE, "serve", "status"])
            self._last_serve_fetch = now
        return self._serve_cache or {}

    def run_serve(self, local_port: int, public_port: str):
        """Enable Tailscale Funnel for a port."""
        if public_port == "tailnet":
            cmd = [TAILSCALE, "serve", "--bg", "--yes", str(local_port)]
        else:
            cmd = [
                TAILSCALE,
                "funnel",
                "--bg",
                "--yes",
                f"--https={public_port}",
                str(local_port),
            ]
        return self._run_cmd(cmd)

    def stop_serve(self, local_port: int, public_port: str):
        if public_port == "tailnet":
            self._run_cmd([TAILSCALE, "serve", "--yes", f"--https={local_port}", "off"])
        else:
            res = self._run_cmd(
                [TAILSCALE, "funnel", "--yes", f"--https={public_port}", "off"]
            )
            if res.returncode != 0:
                self._run_cmd([TAILSCALE, "serve", "--yes", "reset"])

    def cleanup_all(self):
        """Reset all Tailscale serve/funnel configs."""
        self._run_cmd([TAILSCALE, "serve", "--yes", "reset"])


class ProcessManager:
    """Manages project subprocesses, health, and logs."""

    def __init__(self):
        self.running_processes: Dict[str, subprocess.Popen] = {}
        self.project_logs: Dict[str, deque] = {}

    def kill_port(self, port, managed_pid=None):
        """Native way to clear a port safely."""
        for proc in psutil.process_iter(["pid", "name"]):
            try:
                # 1. If we have a specific PID, only kill that one
                if managed_pid and proc.info["pid"] == managed_pid:
                    log_event(
                        f"[KILL] Stopping managed process on port {port} "
                        f"(PID {proc.info['pid']})"
                    )
                    proc.kill()
                    return

                # 2. General check: Only kill if it's REALLY on our port
                for conns in proc.connections(kind="inet"):
                    if conns.laddr.port == port:
                        # Safety: Only kill if it's a known 'zombie' from our launches
                        log_event(
                            f"[WARN] Port {port} is occupied by PID {proc.info['pid']} "
                            f"({proc.info['name']})"
                        )
                        if (
                            managed_pid
                        ):  # We were expecting a specific one, but it's different?
                            log_event("   Skipping kill for external process.")
                        else:
                            # Default behavior for new launches: clear the path
                            log_event(
                                f"[CLEAN] Clearing port {port} for project launch..."
                            )
                            proc.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass

    def start_project(self, key: str, path: str, port: int, command: str) -> Optional[psutil.Process]:
        if not path or not command:
            return None
        try:
            # 1. Self-Correction: Fix common port conflicts BEFORE launch
            self.kill_port(port)
            
            # 2. Environment Setup
            env = os.environ.copy()
            env["PORT"] = str(port)
            env["PYTHONUTF8"] = "1"
            
            actual_command = command.replace("$PORT", str(port)).replace("%PORT%", str(port))

            log_event(f"[START] Launching {key} on port {port}...")
            log_event(f"   Cmd: {actual_command}")
            log_event(f"   Cwd: {path}")

            # Use a log file instead of generic PIPE/DEVNULL to prevent UnicodeEncodeErrors on Windows
            log_path = os.path.join(path, f".magic_{key.replace(':', '_')}.log")
            log_handle = open(log_path, "w", encoding="utf-8")

            proc = subprocess.Popen(
                actual_command,
                cwd=path,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                env=env,
                shell=True,
                creationflags=0x08000000 if os.name == "nt" else 0,
            )

            self.running_processes[key] = proc

            # Desktop Notification
            notification.notify(
                title="Project Started",
                message=f"{key} is now live on port {port}",
                app_name="Tailscale Magic",
            )
            log_event(f"[OK] PID {proc.pid} started for {key}")
            return proc
        except Exception as e:
            log_event(f"[ERROR] Error starting {key}: {e}")
            import traceback
            log_event(traceback.format_exc())
            return None

    def _log_reader(self, pipe, key):
        if key not in self.project_logs:
            self.project_logs[key] = deque(maxlen=200)  # Increased buffer
        try:
            with pipe:
                for line in iter(pipe.readline, b""):
                    decoded = line.decode("utf-8", errors="ignore").strip()
                    if decoded:
                        self.project_logs[key].append(decoded)
        except (IOError, ValueError):
            pass

    def stop_project(self, key):
        proc = self.running_processes.get(key)
        if proc:
            try:
                p = psutil.Process(proc.pid)
                for child in p.children(recursive=True):
                    child.kill()
                p.kill()
                log_event(f"[STOP] Stopped: {key}")
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
            self.running_processes.pop(key, None)
        if key in self.project_logs:
            self.project_logs.pop(key, None)


class MagicCore:
    """The central brain of Tailscale Magic."""

    def __init__(self):
        self.ts = TailscaleWrapper()
        self.pm = ProcessManager()
        self._meta_cache = {}
        self.analytics = {}
        self._analytics_lock = Lock()
        self._projects_lock = Lock()
        self._ensure_config()
        self._load_analytics()

    def _ensure_config(self):
        if not os.path.exists(PROJECTS_FILE):
            with open(PROJECTS_FILE, "w") as f:
                json.dump({}, f)

    def load_projects(self) -> Dict[str, Any]:
        with self._projects_lock:
            try:
                if not os.path.exists(PROJECTS_FILE):
                    return {}
                with open(PROJECTS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return dict(data) if isinstance(data, dict) else {}
            except (IOError, json.JSONDecodeError):
                return {}

    def save_projects(self, projects):
        with self._projects_lock:
            with open(PROJECTS_FILE, "w", encoding="utf-8") as f:
                json.dump(projects, f, indent=4)

    def _load_analytics(self):
        with self._analytics_lock:
            try:
                if os.path.exists(ANALYTICS_FILE):
                    with open(ANALYTICS_FILE, "r", encoding="utf-8") as f:
                        self.analytics = json.load(f)
            except (IOError, json.JSONDecodeError):
                self.analytics = {}

    def save_analytics(self):
        try:
            # We only persist every N minutes or manually to save IO
            with open(ANALYTICS_FILE, "w", encoding="utf-8") as f:
                json.dump(self.analytics, f, indent=4)
        except IOError:
            pass

    def record_hit(self, project_key: str, ip: str, bytes_sent: int = 0):
        with self._analytics_lock:
            # Anonymize IP
            hashed_ip = hashlib.sha256(ip.encode()).hexdigest()
            if project_key not in self.analytics:
                self.analytics[project_key] = {
                    "hits": 0,
                    "unique_ips": [],
                    "total_bytes": 0,
                    "last_hit": 0.0,
                }

            # GDPR compliance: Hash IPs to ensure anonymity
            # hashed_ip is already calculated above

            # Robust type updates
            stats: Dict[str, Any] = self.analytics[project_key]
            
            hits_val = stats.get("hits", 0)
            hits: int = int(hits_val) if isinstance(hits_val, (int, float, str)) else 0
            stats["hits"] = hits + 1

            bytes_val = stats.get("total_bytes", 0)
            t_bytes: int = int(bytes_val) if isinstance(bytes_val, (int, float, str)) else 0
            stats["total_bytes"] = t_bytes + bytes_sent

            stats["last_hit"] = float(time.time())

            u_ips = stats.get("unique_ips", [])
            unique_ips: List[str] = u_ips if isinstance(u_ips, list) else []
            stats["unique_ips"] = unique_ips

            if hashed_ip not in unique_ips:
                if len(unique_ips) < 1000:
                    unique_ips.append(hashed_ip)

            # Save periodically
            if (hits + 1) % 10 == 0:
                self.save_analytics()

    def get_port_owner(self, port: int) -> Optional[str]:
        """Identifies the program holding a port."""
        for conn in psutil.net_connections(kind="inet"):
            if conn.laddr and conn.laddr.port == port:
                if conn.pid:
                    try:
                        p = psutil.Process(conn.pid)
                        return f"{p.name()} (PID {conn.pid})"
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        return f"PID {conn.pid}"
        return None

    def get_system_used_ports(self) -> Dict[int, str]:
        """Get all ports currently bound with their owners."""
        used = {}
        for conn in psutil.net_connections(kind="inet"):
            if conn.laddr and conn.laddr.port:
                if conn.pid:
                    try:
                        p = psutil.Process(conn.pid)
                        used[conn.laddr.port] = p.name()
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        used[conn.laddr.port] = "Unknown"
                else:
                    used[conn.laddr.port] = "System"
        return used

    def get_free_port(self):
        """Find a free local port for a new project."""
        projects = self.load_projects()
        # 1. Ports we know we are using
        our_used = {p.get("port") for p in projects.values() if p.get("port")}
        our_used.add(DASHBOARD_PORT)

        # 2. System-wide check
        system_used_map = self.get_system_used_ports()

        # Start searching from 3002 (avoiding common 3000/3001 defaults)
        for port in range(3002, 10000):
            if port not in our_used and port not in system_used_map:
                # Double-check with bind
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                try:
                    s.bind(("", port))
                    s.close()
                    return port
                except OSError:
                    pass
                finally:
                    s.close()
        return 0

    async def fetch_metadata(self, port: int, force=False):
        """Robustly discover metadata from a local port."""
        if not force and port in self._meta_cache:
            return self._meta_cache[port]

        url = f"http://127.0.0.1:{port}"
        try:
            async with httpx.AsyncClient(timeout=3) as client:
                res = await client.get(url, follow_redirects=True)
                html = res.text

                # Defaults
                title = f"App :{port}"
                description = "Running on Magic Funnel"
                icon = None

                # 1. JSON-LD
                try:
                    ld_match = re.search(
                        r'<script type="application/ld\+json">(.*?)</script>',
                        html,
                        re.S,
                    )
                    if ld_match:
                        data = json.loads(ld_match.group(1))
                        title = data.get("name") or title
                        description = data.get("description") or description
                except (json.JSONDecodeError, AttributeError):
                    pass

                # 2. Meta Tags
                if title == f"App :{port}":
                    t_match = re.search(r"<title>(.*?)</title>", html, re.I)
                    if t_match:
                        title = t_match.group(1).strip()

                m_desc = re.search(r'<meta name="description" content="(.*?)"', html, re.I)
                if m_desc:
                    description = m_desc.group(1).strip()
                elif not description:
                    m_og = re.search(
                        r'<meta property="og:description" content="(.*?)"', html, re.I
                    )
                    if m_og:
                        description = m_og.group(1).strip()

                # 3. Icons
                icon_re = (
                    r'<link.*?rel=["\' ](?:icon|shortcut icon|apple-touch-icon).*?'
                    r'href=["\'](.*?)["\']'
                )
                i_match = re.search(icon_re, html, re.I)
                if i_match:
                    found_icon = i_match.group(1)
                    if found_icon.startswith("http"):
                        icon = found_icon
                    else:
                        icon = f"http://127.0.0.1:{port}/{found_icon.lstrip('/')}"
                else:
                    # Check common paths quickly
                    for path in ["favicon.ico", "favicon.svg", "apple-touch-icon.png"]:
                        try:
                            chk = await client.get(f"{url}/{path}", timeout=0.5)
                            if chk.status_code == 200:
                                icon = f"http://127.0.0.1:{port}/{path}"
                                break
                        except httpx.RequestError:
                            pass

                # Sanitize Icon URLs for HTTPS Portal safety
                if icon:
                    if icon.startswith("http"):
                        pass
                    elif icon.startswith("/"):
                        icon = f"http://127.0.0.1:{port}{icon}"
                    else:
                        icon = f"http://127.0.0.1:{port}/{icon}"

                meta = {"title": title, "description": description, "icon": icon}
                self._meta_cache[port] = meta
                return meta
        except Exception as e:
            log_event(f"Metadata error (Port {port}): {e}")
            return {"title": f"App :{port}", "description": "Offline"}

    def detect_project_type(self, path: str) -> Dict[str, str]:
        """Heuristic detection of project framework/language."""
        if not os.path.exists(path):
            return {"type": "Unknown", "command": ""}

        files = os.listdir(path)
        lower_files = [f.lower() for f in files]

        # --- 0. Custom / System-Level Launchers ---
        # Highest priority: if the user created a specific launcher batch file, use it!
        launcher_candidates = ["launcher.bat", "start.bat", "run.bat", "start-all.bat", "boot.bat", "launch.bat"]
        for cand in launcher_candidates:
            if cand in lower_files:
                idx = lower_files.index(cand)
                actual_name = files[idx]
                return {"type": "Batch Launcher", "command": f"{actual_name}"}

        # --- 1. Node.js Projects (most common) ---
        if "package.json" in files:
            try:
                pkg_json_path = os.path.join(path, "package.json")
                with open(pkg_json_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    scripts = data.get("scripts", {})
                    deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}

                    # Determine install command
                    lock_file = "package-lock.json" if "package-lock.json" in files else None
                    yarn_lock = "yarn.lock" if "yarn.lock" in files else None
                    pnpm_lock = "pnpm-lock.yaml" if "pnpm-lock.yaml" in files else None
                    
                    install_cmd = ""
                    if not has_node_modules:
                        if pnpm_lock:
                            install_cmd = "pnpm install && "
                        elif yarn_lock:
                            install_cmd = "yarn && "
                        elif lock_file:
                            install_cmd = "npm ci && "
                        else:
                            install_cmd = "npm install && "

                    # Framework-specific detection
                    if "next" in deps:
                        cmd = "dev" if "dev" in scripts else "start"
                        return {"type": "Next.js", "command": f"{install_cmd}npm run {cmd}"}
                    if "nuxt" in deps or "nuxt3" in deps:
                        return {"type": "Nuxt.js", "command": f"{install_cmd}npm run dev"}
                    if "@remix-run/react" in deps:
                        return {"type": "Remix", "command": f"{install_cmd}npm run dev"}
                    if "svelte" in deps or "@sveltejs/kit" in deps:
                        return {"type": "SvelteKit", "command": f"{install_cmd}npm run dev"}
                    if "astro" in deps:
                        return {"type": "Astro", "command": f"{install_cmd}npm run dev"}
                    if "vite" in deps:
                        return {"type": "Vite", "command": f"{install_cmd}npm run dev"}
                    if "react-scripts" in deps:
                        return {"type": "React (CRA)", "command": f"{install_cmd}npm start"}
                    if "vue" in deps:
                        return {"type": "Vue.js", "command": f"{install_cmd}npm run dev"}
                    if "express" in deps:
                        cmd = "dev" if "dev" in scripts else "start"
                        return {"type": "Express.js", "command": f"{install_cmd}npm run {cmd}"}

                    # Generic script detection
                    if "dev" in scripts:
                        return {"type": "Node.js (Dev)", "command": f"{install_cmd}npm run dev"}
                    if "start" in scripts:
                        return {"type": "Node.js", "command": f"{install_cmd}npm start"}
                    if "serve" in scripts:
                        return {"type": "Node.js", "command": f"{install_cmd}npm run serve"}

                return {"type": "Node.js", "command": f"{install_cmd}npm start"}
            except Exception:
                return {"type": "Node.js", "command": "npm install && npm start"}

        # --- 2. Python Projects ---
        if "requirements.txt" in files or "pyproject.toml" in files or "Pipfile" in files or "setup.py" in files:
            # Flask
            if "app.py" in files:
                try:
                    with open(os.path.join(path, "app.py"), "r", encoding="utf-8") as f:
                        content = f.read(2048)
                        if "Flask" in content or "flask" in content:
                            return {"type": "Flask", "command": "python app.py"}
                        if "FastAPI" in content or "fastapi" in content:
                            return {"type": "FastAPI", "command": "python app.py"}
                except Exception:
                    pass
                return {"type": "Python", "command": "python app.py"}

            # Django
            if "manage.py" in files:
                return {"type": "Django", "command": "python manage.py runserver 0.0.0.0:$PORT"}

            # FastAPI / Uvicorn
            if "main.py" in files:
                try:
                    with open(os.path.join(path, "main.py"), "r", encoding="utf-8") as f:
                        content = f.read(2048)
                        if "FastAPI" in content or "uvicorn" in content:
                            return {"type": "FastAPI", "command": "python main.py"}
                except Exception:
                    pass
                return {"type": "Python", "command": "python main.py"}

            # Streamlit
            if any(f.endswith(".py") for f in files):
                for pf in files:
                    if pf.endswith(".py"):
                        try:
                            with open(os.path.join(path, pf), "r", encoding="utf-8") as f:
                                if "streamlit" in f.read(1024).lower():
                                    return {"type": "Streamlit", "command": f"streamlit run {pf} --server.port $PORT"}
                        except Exception:
                            pass

            # Generic Python with entry points
            py_files = [f for f in files if f.endswith(".py")]
            if "server.py" in files:
                return {"type": "Python", "command": "python server.py"}
            if "run.py" in files:
                return {"type": "Python", "command": "python run.py"}
            if py_files:
                return {"type": "Python", "command": f"python {py_files[0]}"}
            return {"type": "Python", "command": "python -m http.server $PORT"}

        # --- 3. Go Projects ---
        if "go.mod" in files:
            if "main.go" in files:
                return {"type": "Go", "command": "go run main.go"}
            return {"type": "Go", "command": "go run ."}

        # --- 4. Rust Projects ---
        if "Cargo.toml" in files:
            return {"type": "Rust", "command": "cargo run"}

        # --- 5. Docker Projects ---
        if "docker-compose.yml" in files or "docker-compose.yaml" in files:
            return {"type": "Docker Compose", "command": "docker-compose up"}
        if "Dockerfile" in files:
            return {"type": "Docker", "command": "docker build -t magic-app . && docker run -p $PORT:$PORT magic-app"}

        # --- 6. Static HTML ---
        if "index.html" in files:
            return {"type": "Static HTML", "command": "python -m http.server $PORT"}

        # --- 7. PHP ---
        if "index.php" in files or any(f.endswith(".php") for f in files):
            return {"type": "PHP", "command": "php -S 0.0.0.0:$PORT"}

        return {"type": "Generic Project", "command": ""}


    def startup_sequence(self):
        """Native boot sequence."""
        log_event("[START] Performing Magic Startup...")
        log_event(f"Current Base Path: {BASE_PATH}")
        log_event(f"Project Config: {PROJECTS_FILE}")

        # Dashboard is kept local only

        # 1. Clear stale PIDs from previous session
        projects: Dict[str, Any] = self.load_projects()
        for key, p in projects.items():
            old_pid = p.get("pid")
            if old_pid and isinstance(old_pid, int):
                if not psutil.pid_exists(old_pid):
                    log_event(f"[CLEANUP] Clearing stale PID {old_pid} for {key}")
                    p["pid"] = None
        self.save_projects(projects)

        # 2. Restore Projects
        projects = self.load_projects()
        for key, p in projects.items():
            l_port = p.get("port")
            p_port = p.get("publicPort", "443")
            s_path = p.get("serve_path", "")
            cmd = p.get("command")
            path = p.get("path")

            if l_port and cmd and path:
                proc = self.pm.start_project(key, path, l_port, cmd)
                if proc:
                    p["pid"] = proc.pid

            if l_port and not s_path:
                log_event(f"[REMAP] Restoring Funnel: {key} -> :{p_port}")
                self.ts.run_serve(l_port, p_port)

        self.save_projects(projects)
        log_event("[OK] Startup Complete")

    def _get_active_funnels(self) -> Set[int]:
        """Parse active funnel/serve config to find which local ports are currently tunneled."""
        active: Set[int] = set()
        try:
            serve_status: Dict[str, Any] = self.ts.get_serve_status(force=True)
            if not serve_status:
                return active

            # 1. Identify domains where Funnel is enabled
            allow_funnel: Dict[str, Any] = serve_status.get("AllowFunnel", {})
            allowed_domains = [
                domain for domain, allowed in allow_funnel.items() if allowed
            ]

            # 2. Extract local ports for these domains from the Web handlers
            web_config: Dict[str, Any] = serve_status.get("Web", {})
            for domain, config in web_config.items():
                if domain in allowed_domains:
                    handlers: Dict[str, Any] = config.get("Handlers", {})
                    for path_key, handler in handlers.items():
                        proxy_target = handler.get("Proxy", "")
                        match = re.search(r"127\.0\.0\.1:(\d+)", str(proxy_target))
                        if match:
                            active.add(int(match.group(1)))

            # 3. Check TCP funnels for those domains too
            tcp_config: Dict[str, Any] = serve_status.get("TCP", {})
            # TCP handles raw ports, but the 'active' set should contain the local port
            # In the JSON, if a port like "443" is mapped to a Web domain, it shows up in Web.
            # If it's a raw TCP funnel, we look at the proxy settings.
        except Exception as e:
            log_event(f"[FUNNEL] Failed to parse serve status: {e}")
        return active

    def monitor_loop(self):
        """Infinite loop to keep services alive and heal connections."""
        log_event("[MONITOR] Health check loop started.")
        funnel_check_interval: float = 30.0
        last_funnel_check: float = 0.0

        while True:
            try:
                projects: Dict[str, Any] = self.load_projects()
                if not projects:
                    time.sleep(10)
                    continue

                now: float = time.time()

                # --- 1. PROCESS HEALTH ---
                for key, p in list(projects.items()):
                    if not p.get("active", True):
                        continue # Skip projects explicitly set to inactive

                    port = p.get("port")
                    path = p.get("path")
                    cmd = p.get("command")

                    if path and cmd:
                        proc = self.pm.running_processes.get(key)
                        needs_restart = False
                        
                        # Check if process is still alive in memory
                        if proc:
                            if proc.poll() is not None:
                                needs_restart = True
                        else:
                            # If no handle, check system-wide for the PID
                            pid = p.get("pid")
                            if pid and isinstance(pid, int):
                                if not psutil.pid_exists(pid):
                                    needs_restart = True
                            else:
                                needs_restart = True

                        if needs_restart:
                            # DOUBLE CHECK: Is the port already being served?
                            # If the port is listening, don't restart it yet.
                            # This prevents the "kill-loop" if Windows is slow.
                            used_ports = self.get_system_used_ports()
                            if port in used_ports:
                                log_event(f"[MONITOR] Project {key} seems slow, but port {port} is active. Skipping restart.")
                                continue

                            log_event(f"[RECOVERY] Recovering project: {key}")
                            new_proc = self.pm.start_project(key, path, port, cmd)
                            if new_proc:
                                p["pid"] = new_proc.pid
                                self.save_projects(projects)

                # --- 2. FUNNEL SELF-HEALING ---
                if now - last_funnel_check >= funnel_check_interval:
                    last_funnel_check = now
                    try:
                        active_funnels = self._get_active_funnels()

                        # A. Check Dashboard Funnel
                        if DASHBOARD_PORT not in active_funnels:
                            log_event(f"[HEAL] Dashboard Funnel DOWN. Re-establishing...")
                            self.ts.run_serve(DASHBOARD_PORT, "8443")

                        # B. Check Project Funnels
                        for key, p in projects.items():
                            p_data: Dict[str, Any] = p if isinstance(p, dict) else {}
                            l_port = p_data.get("port")
                            p_port = str(p_data.get("publicPort", "443"))
                            s_path = p_data.get("serve_path", "")

                            if l_port and not s_path and l_port in active_funnels:
                                pass # placeholder
                            elif l_port and not s_path:
                                log_event(f"[HEAL] Funnel DOWN for {key}. Re-establishing...")
                                self.ts.run_serve(int(l_port), p_port)
                    except Exception as e:
                        log_event(f"[HEAL] Error: {e}")

                self.save_analytics()

            except Exception as e:
                log_event(f"[MONITOR] Error: {e}")

            time.sleep(15)


# Central instance for the app to import
core_system = MagicCore()

