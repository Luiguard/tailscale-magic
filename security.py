"""
Security Module — DDoS & Hacking Protection for Tailscale Magic
================================================================
Implements multi-layer protection:
  1. Rate Limiting (per IP, sliding window)
  2. Brute Force Detection (login/API abuse)
  3. Request Validation (payload size, header injection, path traversal)
  4. IP Reputation & Auto-Ban (suspicious patterns)
  5. DDoS Detection (connection flooding)
  
GDPR Compliant: All IPs are hashed before storage. No PII retained.
"""

import time
import hashlib
import re
import os
import json
from collections import defaultdict
from threading import Lock
from typing import Dict, Optional, Set, Tuple

# --- Constants ---
RATE_LIMIT_WINDOW = 60       # seconds
RATE_LIMIT_MAX = 5000        # max requests per window (generous for node_modules/vite/etc)
RATE_LIMIT_BURST = 1000       # max requests in 5 seconds (burst detection)
BURST_WINDOW = 5             # seconds
BAN_DURATION = 300           # 5 minutes ban
BAN_THRESHOLD = 5            # strikes before ban
MAX_BODY_SIZE = 50 * 1024 * 1024  # 50 MB max body
MAX_HEADER_SIZE = 8192       # 8 KB max header value
DDOS_CONN_THRESHOLD = 500    # connections from same IP in 10 seconds = DDoS
DDOS_WINDOW = 10             # seconds

# Suspicious patterns
PATH_TRAVERSAL_PATTERNS = [
    r'\.\.',           # Directory traversal
    r'%2e%2e',         # URL-encoded traversal
    r'%252e%252e',     # Double-encoded
    r'\\\\',           # Windows UNC
    r'/etc/',          # Linux config access
    r'/proc/',         # Linux proc
    r'cmd\.exe',       # Windows command
    r'powershell',     # PowerShell injection
    r'<script',        # XSS attempt
    r'javascript:',    # XSS via protocol
    r'onerror=',       # XSS via event handler
    r'onload=',        # XSS via event handler
    r'UNION\s+SELECT', # SQL injection
    r';\s*DROP\s+',    # SQL injection
    r'--\s*$',         # SQL comment
    r'/wp-admin',      # WordPress scanning
    r'/wp-login',      # WordPress scanning
    r'\.env',          # Environment file access
    r'\.git/',         # Git directory access
    r'\.htaccess',     # Apache config
    r'/phpmyadmin',    # phpMyAdmin scanning
    r'/actuator',      # Spring Boot actuator
    r'/debug/',        # Debug endpoint scanning
]

SUSPICIOUS_USER_AGENTS = [
    'sqlmap',
    'nikto',
    'nmap',
    'masscan',
    'burpsuite',
    'dirbuster',
    'gobuster',
    'wfuzz',
    'hydra',
    'zap',
]


def _hash_ip(ip: str) -> str:
    """GDPR-compliant IP anonymization via SHA256."""
    return hashlib.sha256(ip.encode()).hexdigest()[:16]


class SecurityGuard:
    """Multi-layer security engine for the Magic Portal."""

    def __init__(self, ban_file: Optional[str] = None):
        self._lock = Lock()
        self._request_log: Dict[str, list] = defaultdict(list)     # hashed_ip -> [timestamps]
        self._strike_count: Dict[str, int] = defaultdict(int)      # hashed_ip -> strike count
        self._banned_ips: Dict[str, float] = {}                     # hashed_ip -> ban_until
        self._suspicious_hits: Dict[str, int] = defaultdict(int)   # hashed_ip -> suspicious count
        self._conn_tracker: Dict[str, list] = defaultdict(list)    # hashed_ip -> [timestamps] (DDoS)
        self._compiled_patterns = [re.compile(p, re.IGNORECASE) for p in PATH_TRAVERSAL_PATTERNS]
        self._compiled_ua = [ua.lower() for ua in SUSPICIOUS_USER_AGENTS]
        self._ban_file = ban_file
        self._total_blocked = 0
        self._total_requests = 0
        self._load_bans()

    def _load_bans(self):
        """Load persistent bans from file."""
        if self._ban_file and os.path.exists(self._ban_file):
            try:
                with open(self._ban_file, 'r') as f:
                    data = json.load(f)
                    now = time.time()
                    # Only load bans that haven't expired
                    self._banned_ips = {
                        k: v for k, v in data.items() 
                        if v > now
                    }
            except (json.JSONDecodeError, IOError):
                pass

    def _save_bans(self):
        """Persist ban list to file."""
        if self._ban_file:
            try:
                with open(self._ban_file, 'w') as f:
                    json.dump(self._banned_ips, f, indent=2)
            except IOError:
                pass

    def _cleanup_old_entries(self, hashed_ip: str, now: float):
        """Remove stale timestamps from tracking."""
        cutoff = now - RATE_LIMIT_WINDOW
        if hashed_ip in self._request_log:
            self._request_log[hashed_ip] = [
                t for t in self._request_log[hashed_ip] if t > cutoff
            ]
        cutoff_ddos = now - DDOS_WINDOW
        if hashed_ip in self._conn_tracker:
            self._conn_tracker[hashed_ip] = [
                t for t in self._conn_tracker[hashed_ip] if t > cutoff_ddos
            ]

    def _ban_ip(self, hashed_ip: str, reason: str, duration: float = BAN_DURATION):
        """Ban an IP (hashed) for a duration."""
        self._banned_ips[hashed_ip] = time.time() + duration
        self._save_bans()
        return f"BLOCKED: {reason} (IP hash: {hashed_ip[:8]}...)"

    def check_request(
        self,
        client_ip: str,
        path: str,
        method: str = "GET",
        headers: Optional[dict] = None,
        body_size: int = 0,
    ) -> Tuple[bool, Optional[str]]:
        """
        Main security check. Returns (allowed, reason).
        If allowed=False, reason contains the blocking reason.
        """
        with self._lock:
            self._total_requests += 1
            now = time.time()
            hashed_ip = _hash_ip(client_ip)

            # Whitelist: Localhost, Tailscale (100.x), and Private Network
            if (
                client_ip in ('127.0.0.1', '::1', 'localhost') or 
                client_ip.startswith('100.') or
                client_ip.startswith('192.168.') or
                client_ip.startswith('10.') or
                re.match(r'^172\.(1[6-9]|2[0-9]|3[01])\.', client_ip)
            ):
                return True, None

            self._cleanup_old_entries(hashed_ip, now)

            # --- 1. Check if IP is banned ---
            if hashed_ip in self._banned_ips:
                if now < self._banned_ips[hashed_ip]:
                    self._total_blocked += 1
                    remaining = int(self._banned_ips[hashed_ip] - now)
                    return False, f"IP temporarily banned ({remaining}s remaining)"
                else:
                    # Ban expired
                    del self._banned_ips[hashed_ip]
                    self._strike_count[hashed_ip] = 0

            # --- 2. DDoS Detection (connection flooding) ---
            self._conn_tracker[hashed_ip].append(now)
            if len(self._conn_tracker[hashed_ip]) > DDOS_CONN_THRESHOLD:
                self._total_blocked += 1
                reason = self._ban_ip(hashed_ip, "DDoS detected: connection flooding", BAN_DURATION * 3)
                return False, reason

            # --- 3. Rate Limiting (sliding window) ---
            self._request_log[hashed_ip].append(now)
            request_count = len(self._request_log[hashed_ip])

            if request_count > RATE_LIMIT_MAX:
                self._strike_count[hashed_ip] += 1
                self._total_blocked += 1
                if self._strike_count[hashed_ip] >= BAN_THRESHOLD:
                    reason = self._ban_ip(hashed_ip, "Repeated rate limit violations")
                    return False, reason
                return False, f"Rate limit exceeded ({request_count}/{RATE_LIMIT_MAX} per {RATE_LIMIT_WINDOW}s)"

            # --- 4. Burst Detection ---
            burst_cutoff = now - BURST_WINDOW
            burst_count = sum(1 for t in self._request_log[hashed_ip] if t > burst_cutoff)
            if burst_count > RATE_LIMIT_BURST:
                self._suspicious_hits[hashed_ip] += 1
                self._total_blocked += 1
                if self._suspicious_hits[hashed_ip] >= BAN_THRESHOLD:
                    reason = self._ban_ip(hashed_ip, "Burst flood detected")
                    return False, reason
                return False, f"Burst limit exceeded ({burst_count}/{RATE_LIMIT_BURST} in {BURST_WINDOW}s)"

            # --- 5. Body Size Check ---
            if body_size > MAX_BODY_SIZE:
                self._total_blocked += 1
                return False, f"Request body too large ({body_size} bytes, max {MAX_BODY_SIZE})"

            # --- 6. Path Traversal / Injection Detection ---
            for pattern in self._compiled_patterns:
                if pattern.search(path):
                    self._suspicious_hits[hashed_ip] += 1
                    self._total_blocked += 1
                    if self._suspicious_hits[hashed_ip] >= 2:
                        reason = self._ban_ip(hashed_ip, f"Malicious path pattern: {pattern.pattern}")
                        return False, reason
                    return False, f"Suspicious request path blocked: {pattern.pattern}"

            # --- 7. User-Agent Analysis ---
            if headers:
                ua = (headers.get('user-agent') or '').lower()
                for suspicious_ua in self._compiled_ua:
                    if suspicious_ua in ua:
                        self._total_blocked += 1
                        reason = self._ban_ip(hashed_ip, f"Malicious scanner detected: {suspicious_ua}")
                        return False, reason

                # Check for missing or abnormally short User-Agent
                if len(ua) < 5 and method not in ('OPTIONS', 'HEAD'):
                    self._suspicious_hits[hashed_ip] += 1

                # Check header injection
                for key, value in headers.items():
                    if isinstance(value, str) and len(value) > MAX_HEADER_SIZE:
                        self._total_blocked += 1
                        return False, f"Header value too large: {key}"
                    if isinstance(value, str) and ('\r' in value or '\n' in value):
                        self._total_blocked += 1
                        reason = self._ban_ip(hashed_ip, "Header injection attempt")
                        return False, reason

            return True, None

    def get_stats(self) -> dict:
        """Return security statistics for the dashboard."""
        with self._lock:
            now = time.time()
            active_bans = {
                k: int(v - now) 
                for k, v in self._banned_ips.items() 
                if v > now
            }
            return {
                'total_requests': self._total_requests,
                'total_blocked': self._total_blocked,
                'active_bans': len(active_bans),
                'ban_details': active_bans,
                'tracked_ips': len(self._request_log),
                'block_rate': f"{(self._total_blocked / max(self._total_requests, 1)) * 100:.1f}%",
            }

    def unban_all(self):
        """Emergency unban all IPs."""
        with self._lock:
            self._banned_ips.clear()
            self._strike_count.clear()
            self._suspicious_hits.clear()
            self._save_bans()

    def unban_ip(self, hashed_ip_prefix: str) -> bool:
        """Unban a specific IP by hash prefix."""
        with self._lock:
            to_remove = [k for k in self._banned_ips if k.startswith(hashed_ip_prefix)]
            for k in to_remove:
                del self._banned_ips[k]
            if to_remove:
                self._save_bans()
                return True
            return False
