import * as BABYLON from 'babylonjs';
import * as GUI from 'babylonjs-gui';
import { Building, BuildingData } from './Building';

export class CityEngine {
    private static readonly VERSION = "1.1.2";
    private engine: BABYLON.Engine;
    private scene: BABYLON.Scene;
    private canvas: HTMLCanvasElement;
    private buildings: Building[] = [];
    private lampMat: BABYLON.StandardMaterial | null = null;

    constructor(canvas: HTMLCanvasElement) {
        console.log(`[3D] CityEngine v${CityEngine.VERSION} initializing...`);
        this.canvas = canvas;
        this.engine = new BABYLON.Engine(this.canvas, true);
        this.scene = new BABYLON.Scene(this.engine);
        this.setupScene();
    }

    private setupScene() {
        // Atmosphere & Lighting
        this.scene.clearColor = new BABYLON.Color4(0.01, 0.01, 0.03, 1);
        this.scene.fogEnabled = true;
        this.scene.fogMode = BABYLON.Scene.FOGMODE_EXP;
        this.scene.fogDensity = 0.003;
        this.scene.fogColor = new BABYLON.Color3(0.01, 0.01, 0.04);

        const light = new BABYLON.DirectionalLight("moon", new BABYLON.Vector3(0.5, -1, 0.5), this.scene);
        light.intensity = 0.8;
        light.diffuse = new BABYLON.Color3(0.4, 0.6, 1);

        const ambient = new BABYLON.HemisphericLight("ambient", new BABYLON.Vector3(0, 1, 0), this.scene);
        ambient.intensity = 0.4;

        // Global Glow Layer
        const glow = new BABYLON.GlowLayer("glow", this.scene);
        glow.intensity = 0.8;

        this.setupAudio();
        this.createGround();
        this.setupUI();
        this.setupInteractions();

        // Performance Optimization: Freeze materials and optimize scene
        this.scene.performancePriority = BABYLON.ScenePerformancePriority.BackwardCompatible;
        this.scene.blockfreeActiveMeshesAndRenderingGroups = true;

        // [STEP-BY-STEP REASSEMBLY: ENABLED]
        this.createBackgroundCity();
        this.createStarfield();

        // Let the scene settle before intensive optimizations
        setTimeout(() => {
            this.scene.blockfreeActiveMeshesAndRenderingGroups = false;
            this.scene.freezeMaterials();
        }, 3000);

        // Debugging & Hotfix Keys
        window.addEventListener("keydown", (ev) => {
            // Shift + I: Inspector
            if (ev.shiftKey && ev.keyCode === 73) {
                if (this.scene.debugLayer.isVisible()) {
                    this.scene.debugLayer.hide();
                } else {
                    import('babylonjs-inspector');
                    this.scene.debugLayer.show();
                }
            }
            // L: Reload World (Hotfix size/pos)
            if (ev.keyCode === 76) {
                console.log("[3D] Triggering World Regeneration...");
                this.loadWorld();
            }
            // O: Toggle Outlines / Debug Info
            if (ev.keyCode === 79) {
                this.buildings.forEach(b => {
                    const plane = b.container.getChildMeshes().find(m => m.name === "info");
                    if (plane) plane.isVisible = !plane.isVisible;
                });
            }
        });
    }

    private createBackgroundCity() {
        const mat = new BABYLON.StandardMaterial("bgMat", this.scene);
        mat.emissiveColor = new BABYLON.Color3(0.05, 0.05, 0.1);
        mat.diffuseColor = new BABYLON.Color3(0.1, 0.1, 0.2);
        mat.alpha = 0.4;

        for (let i = 0; i < 60; i++) {
            const h = 80 + Math.random() * 200;
            const w = 25 + Math.random() * 15;

            // Create tapered background towers
            const tower = BABYLON.MeshBuilder.CreateCylinder("bgTower", {
                height: h,
                diameterTop: w * 0.5,
                diameterBottom: w,
                tessellation: 4 // Square base
            }, this.scene);

            const r = 500 + Math.random() * 500;
            const ang = Math.random() * Math.PI * 2;
            tower.position.set(Math.cos(ang) * r, h / 2 - 5, Math.sin(ang) * r);
            tower.rotation.y = Math.random() * Math.PI;
            tower.material = mat;
        }
    }

    private createStarfield() {
        const starCount = 1000;
        const positions = [];
        const colors = [];

        for (let i = 0; i < starCount; i++) {
            const r = 900;
            const theta = Math.random() * 2 * Math.PI;
            const phi = Math.acos(2 * Math.random() - 1);

            positions.push(
                r * Math.sin(phi) * Math.cos(theta),
                r * Math.sin(phi) * Math.sin(theta),
                r * Math.cos(phi)
            );

            const intensity = 0.5 + Math.random() * 0.5;
            colors.push(intensity, intensity, 1, 1);
        }

        const mesh = new BABYLON.Mesh("stars", this.scene);
        const vertexData = new BABYLON.VertexData();
        vertexData.positions = positions;
        vertexData.colors = colors;
        vertexData.applyToMesh(mesh);

        const starMat = new BABYLON.StandardMaterial("starMat", this.scene);
        starMat.emissiveColor = new BABYLON.Color3(1, 1, 1);
        starMat.disableLighting = true;
        starMat.pointsCloud = true;
        starMat.pointSize = 2;
        mesh.material = starMat;
    }

    private setupAudio() {
        new BABYLON.Sound("Ambient", "https://actions.google.com/sounds/v1/science_fiction/glitchy_data_processing.ogg", this.scene, null, {
            loop: true,
            autoplay: true,
            volume: 0.1
        });
    }

    private setupUI() {
        const advancedTexture = GUI.AdvancedDynamicTexture.CreateFullscreenUI("UI");

        // Reticle / Crosshair
        const reticle = new GUI.Ellipse("reticle");
        reticle.width = "10px";
        reticle.height = "10px";
        reticle.color = "cyan";
        reticle.thickness = 2;
        advancedTexture.addControl(reticle);

        const label = new GUI.TextBlock("instruction-label");
        label.text = "NACHRICHT: VISIER AUF GEBÄUDE RICHTEN";
        label.color = "rgba(0, 255, 255, 0.5)";
        label.fontSize = 20;
        label.top = "40px";
        advancedTexture.addControl(label);

        // Responsive & Interactive Credits
        const creditsContainer = new GUI.Rectangle("credits-container");
        creditsContainer.height = "auto";
        creditsContainer.width = "100%";
        creditsContainer.thickness = 0;
        creditsContainer.verticalAlignment = GUI.Control.VERTICAL_ALIGNMENT_BOTTOM;
        creditsContainer.top = "-20px"; // Adjust this if you add a bottom bar
        advancedTexture.addControl(creditsContainer);

        const creditsPanel = new GUI.StackPanel("credits-stack");
        creditsPanel.isVertical = false;
        creditsPanel.height = "30px";
        creditsContainer.addControl(creditsPanel);

        // Adjust layout for narrow screens
        const checkResize = () => {
            const isNarrow = this.canvas.width < 600;
            creditsPanel.isVertical = isNarrow;
            creditsPanel.height = isNarrow ? "auto" : "30px";
            creditsContainer.height = isNarrow ? "auto" : "30px";
        };
        this.engine.onResizeObservable.add(checkResize);
        setTimeout(checkResize, 0);

        const addCredit = (text: string, url?: string) => {
            const block = new GUI.TextBlock(`credit-${text.substring(0, 10).trim()}`);
            block.text = text;
            block.color = "white";
            block.fontSize = 12;
            block.width = "120px"; // Explicit pixel width to avoid percentage warnings
            block.resizeToFit = false;
            block.paddingLeft = "4px";
            block.paddingRight = "4px";
            block.lineSpacing = "2px";

            if (url) {
                block.isPointerBlocker = true;
                block.onPointerDownObservable.add(() => block.color = "#00ffff");
                block.onPointerUpObservable.add(() => {
                    block.color = "#06b6d4";
                    window.open(url, '_blank');
                });
                block.onPointerEnterObservable.add(() => block.color = "#06b6d4");
                block.onPointerOutObservable.add(() => block.color = "white");
                block.hoverCursor = "pointer";
            }
            creditsPanel.addControl(block);
        };

        addCredit("Trees", "https://poly.pizza/m/etFGNvsiFv");
        addCredit(" by Quaternius  | ");
        addCredit("City Pack", "https://poly.pizza/bundle/City-Pack-kJqRAIGsw0");
        addCredit(" by ");
        addCredit("J-Toastie", "https://poly.pizza/u/J-Toastie");
        addCredit(" [");
        addCredit("CC-BY", "https://creativecommons.org/licenses/by/3.0/");
        addCredit("] via Poly Pizza");
    }

    private setupInteractions() {
        this.scene.onPointerDown = (_evt: BABYLON.IPointerEvent, pickResult: BABYLON.PickingInfo) => {
            if (pickResult.hit && pickResult.pickedMesh) {
                let mesh = pickResult.pickedMesh;
                // Traverse up to find the container with metadata
                let current: BABYLON.Node | null = mesh;
                while (current) {
                    if (current.metadata && current.metadata.url) {
                        window.open(current.metadata.url, '_blank');
                        return;
                    }
                    current = current.parent;
                }
            }
        };
    }

    private setupStreets() {
        // Build a strict grid every 200 units (5x5 grid for better performance)
        for (let i = -2; i <= 2; i++) {
            this.createAdvancedStreet(i * 200, false); // N-S
            this.createAdvancedStreet(i * 200, true);  // E-W
        }
    }

    private createAdvancedStreet(offset: number, isHorizontal: boolean) {
        const group = new BABYLON.TransformNode("street-group", this.scene);

        // Tech Road Plane (Underneath for seamless color)
        const roadWidth = 32;
        const road = BABYLON.MeshBuilder.CreatePlane("road-base", { width: roadWidth, height: 2000 }, this.scene);
        road.rotation.x = Math.PI / 2;
        if (isHorizontal) road.rotation.y = Math.PI / 2;
        road.position.set(isHorizontal ? 0 : offset, -2.05, isHorizontal ? offset : 0);

        const roadMat = new BABYLON.StandardMaterial("roadMat", this.scene);
        roadMat.diffuseTexture = new BABYLON.Texture("/static/assets/tech_road.png", this.scene);
        if (roadMat.diffuseTexture) (roadMat.diffuseTexture as BABYLON.Texture).vScale = 40;
        road.material = roadMat;
        road.parent = group;

        // Place "Road Bits" meshes for actual geometry
        for (let lz = -1000; lz <= 1000; lz += 40) {
            const bit = Building.getProp("Road Bits", group);
            if (bit) {
                const px = isHorizontal ? lz : offset;
                const pz = isHorizontal ? offset : lz;
                bit.position.set(px, -2.0, pz);

                // Use robust normalized scale instead of hardcoded factor
                if (bit instanceof BABYLON.TransformNode) {
                    Building.applyNormalizedScale(bit, 0.5); // Thin road strip
                }

                if (isHorizontal) bit.rotation.y = Math.PI / 2;

                // Only freeze AFTER positioning and scaling
                bit.getChildMeshes().forEach(m => {
                    m.freezeWorldMatrix();
                    m.cullingStrategy = BABYLON.AbstractMesh.CULLINGSTRATEGY_BOUNDINGSPHERE_ONLY;
                });
            }
        }

        // Sidewalks & Props
        [22, -22].forEach(sideOffset => {
            const sidewalk = BABYLON.MeshBuilder.CreateBox("sidewalk", { width: 12, height: 1, depth: 2000 }, this.scene);
            if (isHorizontal) sidewalk.rotation.y = Math.PI / 2;

            const px = isHorizontal ? 0 : offset + sideOffset;
            const pz = isHorizontal ? offset + sideOffset : 0;
            sidewalk.position.set(px, -2.0, pz);

            const sideMat = new BABYLON.StandardMaterial("sideMat", this.scene);
            sideMat.diffuseTexture = new BABYLON.Texture("/static/assets/sidewalk.png", this.scene);
            if (sideMat.diffuseTexture) (sideMat.diffuseTexture as BABYLON.Texture).vScale = 40;
            sidewalk.material = sideMat;
            sidewalk.parent = group;
            sidewalk.checkCollisions = true;

            for (let lz = -800; lz < 800; lz += 120) {
                const lpX = isHorizontal ? lz : offset + sideOffset;
                const lpZ = isHorizontal ? offset + sideOffset : lz;
                this.createLamps(lpX, lpZ, group);

                if (Math.random() > 0.4) {
                    const propX = isHorizontal ? lz + 30 : offset + sideOffset - (sideOffset > 0 ? 4 : -4);
                    const propZ = isHorizontal ? offset + sideOffset - (sideOffset > 0 ? 4 : -4) : lz + 30;
                    this.createProp(propX, propZ, isHorizontal, group);
                }
            }
        });
    }

    private createProp(x: number, z: number, isHorizontal: boolean, parent: BABYLON.TransformNode) {
        const propNames = ["Bench", "Trash Can", "Mailbox", "Fire hydrant", "Traffic Light", "Stop sign", "Bus Stop", "Manhole Cover"];
        const name = propNames[Math.floor(Math.random() * propNames.length)];
        const prop = Building.getProp(name, parent);
        if (prop) {
            prop.position.set(x, -1.9, z);

            // CRITICAL: Be careful with normalization height targets
            let targetH: number | null = 2.5; // Default for bench/trash
            if (name === "Traffic Light") targetH = 8;
            else if (name === "Stop sign") targetH = 6;
            else if (name === "Bus Stop") targetH = 7;
            else if (name === "Fire hydrant") targetH = 1.5;
            else if (name === "Manhole Cover") targetH = null; // Skip normalization for flat items!

            if (prop instanceof BABYLON.TransformNode) {
                if (targetH !== null) {
                    Building.applyNormalizedScale(prop, targetH);
                } else {
                    prop.scaling.set(4, 4, 4); // Fixed scale for flat items like manhole covers
                }
            }

            prop.rotation.y = isHorizontal ? 0 : Math.PI / 2;
        }
    }

    private createLamps(x: number, z: number, parent: BABYLON.TransformNode) {
        // Optimization: real spotlights (200+) exceed hardware limits (MAX_VERTEX_UNIFORM_BUFFERS).
        // We use emissive materials + Glow Layer for a neon effect.
        const lampGroup = new BABYLON.TransformNode("lamp-group", this.scene);
        lampGroup.position.set(x, -2, z);
        lampGroup.parent = parent;

        if (!this.lampMat) {
            this.lampMat = new BABYLON.StandardMaterial("lampHeadMat", this.scene);
            this.lampMat.emissiveColor = new BABYLON.Color3(0, 1, 1);
            this.lampMat.diffuseColor = new BABYLON.Color3(0, 0, 0);
        }

        BABYLON.MeshBuilder.CreateBox("lamp-base", { width: 1.5, height: 1, depth: 1.5 }, this.scene).parent = lampGroup;

        const pole = BABYLON.MeshBuilder.CreateCylinder("lamp-pole", { height: 16, diameterTop: 0.2, diameterBottom: 0.6 }, this.scene);
        pole.position.y = 8;
        pole.parent = lampGroup;

        const arm = BABYLON.MeshBuilder.CreateBox("lamp-arm", { width: 4, height: 0.4, depth: 0.4 }, this.scene);
        arm.position.set(1.5, 16, 0);
        arm.parent = lampGroup;

        const head = BABYLON.MeshBuilder.CreateBox("lamp-head", { width: 2, height: 0.8, depth: 1.2 }, this.scene);
        head.position.set(3, 16, 0);
        head.parent = lampGroup;
        head.material = this.lampMat;

        // Freeze static parts
        lampGroup.getChildMeshes().forEach(m => m.freezeWorldMatrix());
    }

    private createGround() {
        const ground = BABYLON.MeshBuilder.CreateGround("ground", { width: 2000, height: 2000 }, this.scene);
        ground.position.y = -2.1;
        const groundMat = new BABYLON.StandardMaterial("gMat", this.scene);
        const tex = new BABYLON.Texture("/static/assets/tech_ground.png", this.scene);
        tex.uScale = 40;
        tex.vScale = 40;
        groundMat.diffuseTexture = tex;
        groundMat.diffuseColor = new BABYLON.Color3(0.2, 0.2, 0.3);
        ground.material = groundMat;
        ground.receiveShadows = true;
        ground.checkCollisions = true;

        this.addDataParticles();
    }

    private addDataParticles() {
        const system = new BABYLON.ParticleSystem("data-rain", 2000, this.scene);
        // Use a generic spark texture instead of a failing external URL
        system.particleTexture = new BABYLON.Texture("https://assets.babylonjs.com/textures/flare.png", this.scene);

        system.emitter = new BABYLON.Vector3(0, 50, 0);
        system.minEmitBox = new BABYLON.Vector3(-500, 0, -500);
        system.maxEmitBox = new BABYLON.Vector3(500, 0, 500);

        system.color1 = new BABYLON.Color4(0, 1, 1, 1);
        system.color2 = new BABYLON.Color4(0.5, 0.5, 1, 1);
        system.minSize = 0.1;
        system.maxSize = 0.3;
        system.minLifeTime = 2.0;
        system.maxLifeTime = 5.0;
        system.emitRate = 500;

        system.gravity = new BABYLON.Vector3(0, -9.81, 0);
        system.direction1 = new BABYLON.Vector3(0, -1, 0);
        system.direction2 = new BABYLON.Vector3(0, -1, 0);

        system.start();
    }

    public async loadWorld(onProgress?: (percent: number) => void) {
        try {
            console.log("[3D] Reloading World...");
            // 1. Cleanup all city nodes explicitly
            this.buildings.forEach(b => b.container.dispose());
            this.buildings = [];

            // Dispose all city-related nodes from the root
            this.scene.rootNodes.slice().forEach(node => {
                const names = ["street-group", "building-container", "parcel", "lamp-group"];
                if (names.includes(node.name)) node.dispose();
            });

            // 2. Preload 3D Assets with progress tracking
            await Building.preloadAssets(this.scene, onProgress);

            const res = await fetch('/portal/services.json');
            const data = await res.json();
            const analytics = await fetch('/api/analytics').then(r => r.json());
            const services = data.services || [];

            const occupiedSlots = new Set<string>();

            // 1. Place Services
            services.forEach((s: any, i: number) => {
                const stats = analytics[s.key] || { hits: 0 };
                const bData: BuildingData = {
                    name: s.name,
                    url: s.url,
                    icon_url: s.icon_url,
                    hits: stats.hits,
                    is_public: s.is_public
                };

                const building = new Building(this.scene, bData);
                const pos = this.placeBuilding(building.container, i);
                occupiedSlots.add(`${pos.col},${pos.row}`);
                this.buildings.push(building);
            });

            // 2. [READY FOR NEXT STEP: Decoration Buildings]
            /*
            const citySize = 5; 
            for (let c = -citySize; c <= citySize; c++) {
                for (let r = -citySize; r <= citySize; r++) {
                    if (occupiedSlots.has(`${c},${r}`)) continue;
                    // ... create deco ...
                }
            }
            */

            this.setupStreets();

            // Add a slight delay before freezing materials/world to let everything settle
            setTimeout(() => {
                this.buildings.forEach(b => {
                    b.container.getChildMeshes().forEach(m => m.freezeWorldMatrix());
                });
            }, 1000);

        } catch (e) {
            console.error("Failed to load world:", e);
        }
    }

    private placeBuilding(mesh: BABYLON.Mesh, index: number): { col: number, row: number } {
        // Place in specific "Blocks" (The gaps between grid lines)
        const cols = 4;
        const col = (index % cols) - (cols / 2);
        const row = Math.floor(index / cols) - 1;

        const x = (col * 200) + 100;
        const z = (row * 200) + 100;

        mesh.position.set(x, -2, z);
        mesh.checkCollisions = true;
        mesh.getChildMeshes().forEach(m => m.checkCollisions = true);

        return { col, row };
    }

    public start() {
        const camera = new BABYLON.UniversalCamera("hero", new BABYLON.Vector3(100, 15, 250), this.scene);
        camera.setTarget(new BABYLON.Vector3(100, 0, 100));
        camera.attachControl(this.canvas, true);

        camera.speed = 2.5;
        camera.inertia = 0.9;

        this.scene.gravity = new BABYLON.Vector3(0, -0.9, 0);
        this.scene.collisionsEnabled = true;

        camera.applyGravity = true;
        camera.checkCollisions = true;
        camera.ellipsoid = new BABYLON.Vector3(2, 4, 2);

        // WASD
        camera.keysUp.push(87);
        camera.keysDown.push(83);
        camera.keysLeft.push(65);
        camera.keysRight.push(68);

        this.engine.runRenderLoop(() => {
            this.scene.render();
        });

        window.addEventListener("resize", () => this.engine.resize());
    }

    public dispose() {
        this.engine.dispose();
    }
}
