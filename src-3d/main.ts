import { CityEngine } from './CityEngine';

let currentEngine: CityEngine | null = null;

export function init3D(viewportId: string) {
    const viewport = document.getElementById(viewportId);
    if (!viewport) return;

    // Create Loading UI
    const loadingOverlay = document.createElement("div");
    loadingOverlay.id = "magic-3d-loading";
    loadingOverlay.style.cssText = `
        position: absolute; top:0; left:0; width:100%; height:100%;
        background: radial-gradient(circle at center, #0a0f1e 0%, #020408 100%);
        display: flex; flex-direction: column; align-items: center; justify-content: center;
        z-index: 1000; transition: opacity 0.8s ease-out; font-family: 'Outfit', sans-serif;
    `;

    loadingOverlay.innerHTML = `
        <div style="margin-bottom: 2rem; text-align: center;">
            <i class="fas fa-wand-magic-sparkles" style="font-size: 3rem; color: #06b6d4; margin-bottom: 1rem; display: block; filter: drop-shadow(0 0 15px rgba(6,182,212,0.5)); animation: float 3s ease-in-out infinite;"></i>
            <h2 style="color: white; letter-spacing: 2px; text-transform: uppercase; font-size: 1.2rem;">Initialisiere Holodeck</h2>
            <p id="loading-status" style="color: #94a3b8; font-size: 0.9rem; margin-top: 0.5rem;">Lade Assets... 0%</p>
        </div>
        <div style="width: 300px; height: 4px; background: rgba(255,255,255,0.05); border-radius: 10px; overflow: hidden; border: 1px solid rgba(255,255,255,0.1);">
            <div id="loading-bar" style="width: 0%; height: 100%; background: linear-gradient(90deg, #3b82f6, #06b6d4); transition: width 0.3s ease-out; box-shadow: 0 0 10px rgba(6,182,212,0.5);"></div>
        </div>
    `;
    viewport.appendChild(loadingOverlay);

    const canvas = document.createElement("canvas");
    canvas.style.width = "100%";
    canvas.style.height = "100%";
    viewport.appendChild(canvas);

    currentEngine = new CityEngine(canvas);

    // Pass callback to update loading bar
    currentEngine.loadWorld((percent) => {
        const bar = document.getElementById("loading-bar");
        const status = document.getElementById("loading-status");
        if (bar) bar.style.width = `${percent}%`;
        if (status) status.innerText = `Lade Assets... ${percent}%`;

        if (percent >= 100) {
            setTimeout(() => {
                loadingOverlay.style.opacity = "0";
                setTimeout(() => loadingOverlay.remove(), 800);
            }, 500);
        }
    });

    currentEngine.start();
}

export function stop3D() {
    if (currentEngine) {
        currentEngine.dispose();
        currentEngine = null;
    }
}

// Attach to window for the legacy portal.html toggle to find
(window as any).Magic3D = { init: init3D, stop: stop3D };
