# 🪄 Tailscale Magic

**The ultimate platform to instantly host, share, and manage local AI & web projects securely via Tailscale Funnel. Features include auto-detection, multi-service proxying, DDoS protection, and a premium dashboard.**

---

## 🌟 Overview

Tailscale Magic is a self-hosted platform designed for developers and AI agents who need to bridge local development projects with the outside world securely. It leverages **Tailscale Funnel** to provide encrypted, authenticated, and publicly accessible URLs for your local services without complex firewall or VPN configurations.

## 🚀 Key Features

*   **⚡ One-Click Hosting**: Automatically detect and launch projects (Vite, Next.js, Flask, FastAPI, Go, Rust, etc.).
*   **🛡️ Security Guard**: Built-in DDoS protection, IP whitelisting, rate limiting, and malicious pattern detection.
*   **🎨 Premium Dashboard**: A beautiful, desktop-native interface to monitor project health, logs, and traffic analytics.
*   **🔄 Integrated Reverse Proxy**: Unified routing for multiple local services through a single Tailscale domain.
*   **🤖 AI-Agent Friendly**: Optimized for autonomous agents to register and manage services via a simple JSON registry.
*   **🧩 Framework Agnostic**: Intelligent heuristic detection for virtually any framework or library.

## 🛠️ Installation & Setup

### Prerequisites
*   [Tailscale](https://tailscale.com/) installed and logged in.
*   [Tailscale Funnel](https://tailscale.com/kb/1223/funnel/) enabled on your Tailnet.
*   Python 3.10+ installed.

### Quick Start
1.  **Clone the Repository**:
    ```bash
    git clone https://github.com/Luiguard/tailscale-magic.git
    cd tailscale-magic
    ```
2.  **Install Dependencies**:
    ```bash
    pip install -r requirements.txt
    ```
3.  **Run with Magic**:
    ```bash
    python main.py
    ```
    *Alternatively, use `Start Magic.bat` on Windows.*

## 📂 Configuration

Projects are registered in `projects.json`. An AI agent can also use the `AI_MAGIC_GUIDE.md` for standardized registration.

```json
{
  "my-app": {
    "path": "C:/Projects/my-app",
    "port": 3000,
    "publicPort": "443",
    "name": "My AI Project",
    "command": "npm run dev"
  }
}
```

## ⚖️ License

This project is licensed under the **MIT License** — feel free to use it, modify it, and share it with the world.

---

**Crafted with 🪄 by [Luiguard (Benjamin Leimer)](https://github.com/Luiguard)**
