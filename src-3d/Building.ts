import * as BABYLON from 'babylonjs';
import 'babylonjs-loaders';
import * as GUI from 'babylonjs-gui';

export interface BuildingData {
    name: string;
    url: string;
    icon_url?: string;
    hits: number;
    is_public: boolean;
    isDeco?: boolean;
}

export class Building {
    public container: BABYLON.Mesh;
    private scene: BABYLON.Scene;

    // Use a static object to store assets, making it easier to track and access
    private static Assets: {
        buildings: BABYLON.AbstractMesh[][],
        cars: BABYLON.AbstractMesh[][],
        trees: BABYLON.AbstractMesh[][],
        props: { [key: string]: BABYLON.AbstractMesh[] }
    } = { buildings: [], cars: [], trees: [], props: {} };

    public static async preloadAssets(scene: BABYLON.Scene, onProgress?: (percent: number) => void) {
        console.log("[3D] Clearing and Preloading Assets...");

        // CRITICAL: Clear existing static assets to prevent duplicates on reload
        this.Assets.buildings = [];
        this.Assets.cars = [];
        this.Assets.trees = [];
        this.Assets.props = {};

        const packPath = "/static/assets/city_pack/";

        const filesToLoad = [
            { folder: "/static/assets/", file: "Trees.glb" },
            { folder: packPath, file: "Big Building.glb" },
            { folder: packPath, file: "Brown Building.glb" },
            { folder: packPath, file: "Building Green.glb" },
            { folder: packPath, file: "Building Red.glb" },
            { folder: packPath, file: "Pizza Corner.glb" },
            { folder: packPath, file: "Car.glb" },
            { folder: packPath, file: "SUV.glb" },
            { folder: packPath, file: "Sports Car.glb" },
            { folder: packPath, file: "Pickup Truck.glb" },
            { folder: packPath, file: "Van.glb" },
            { folder: packPath, file: "Bench.glb" },
            { folder: packPath, file: "Trash Can.glb" },
            { folder: packPath, file: "Mailbox.glb" },
            { folder: packPath, file: "Fire hydrant.glb" },
            { folder: packPath, file: "ATM.glb" },
            { folder: packPath, file: "Road Bits.glb" },
            { folder: packPath, file: "Traffic Light.glb" },
            { folder: packPath, file: "Stop sign.glb" },
            { folder: packPath, file: "Bus Stop.glb" },
            { folder: packPath, file: "Manhole Cover.glb" }
        ];

        let loadedCount = 0;
        const totalCount = filesToLoad.length;

        const loadFile = async (folder: string, file: string) => {
            try {
                const res = await BABYLON.SceneLoader.ImportMeshAsync("", folder, file, scene);
                loadedCount++;
                if (onProgress) onProgress(Math.floor((loadedCount / totalCount) * 100));

                if (res.meshes.length > 0) {
                    res.meshes.forEach(m => {
                        m.setEnabled(false);
                        // Do not freeze the master meshes, it breaks scaling calculation for clones
                        m.doNotSyncBoundingInfo = false;
                    });
                    return res.meshes;
                }
            } catch (err) {
                console.error(`[3D] Failed to load: ${file}`, err);
                loadedCount++;
                if (onProgress) onProgress(Math.floor((loadedCount / totalCount) * 100));
            }
            return null;
        };

        try {
            const results = await Promise.all(filesToLoad.map(f => loadFile(f.folder, f.file)));

            const treeMeshes = results[0];
            if (treeMeshes) this.Assets.trees.push(treeMeshes);

            const buildingRes = results.slice(1, 6);
            const carRes = results.slice(6, 11);
            const propRes = results.slice(11);

            buildingRes.forEach(m => { if (m) this.Assets.buildings.push(m); });
            carRes.forEach(m => { if (m) this.Assets.cars.push(m); });

            const propKeys = ["Bench", "Trash Can", "Mailbox", "Fire hydrant", "ATM", "Road Bits", "Traffic Light", "Stop sign", "Bus Stop", "Manhole Cover"];
            propRes.forEach((m, i) => { if (m && propKeys[i]) this.Assets.props[propKeys[i]] = m; });

            console.log(`[3D] Preload complete. Buildings: ${this.Assets.buildings.length}, Cars: ${this.Assets.cars.length}`);
        } catch (e) {
            console.error("[3D] Critical failure in preloadAssets:", e);
        }
    }

    /**
     * Optimized Normalized Scaling
     * Ensures an object reaches a target height regardless of the original model's scale.
     */
    public static applyNormalizedScale(node: BABYLON.TransformNode, targetHeight: number) {
        // Force the node and all its children to compute their bounds from scratch
        node.scaling.set(1, 1, 1);
        node.computeWorldMatrix(true);
        node.getChildMeshes().forEach(m => {
            m.unfreezeWorldMatrix();
            m.computeWorldMatrix(true);
        });

        const bounds = node.getHierarchyBoundingVectors(true);
        const currentHeight = bounds.max.y - bounds.min.y;

        if (currentHeight > 0.1) { // Avoid division by near-zero resulting in giants
            const scale = targetHeight / currentHeight;
            node.scaling.set(scale, scale, scale);
            node.computeWorldMatrix(true);
        } else {
            console.warn(`[3D] Refusing to scale near-zero height node: ${node.name}`);
        }
    }

    /**
     * Creates an instance of a prop. Uses InstancedMesh for better performance
     * if the prop consists of only one mesh, otherwise falls back to cloning.
     */
    public static getProp(name: string, parent: BABYLON.TransformNode): BABYLON.AbstractMesh | BABYLON.TransformNode | null {
        const masters = this.Assets.props[name];
        if (!masters || masters.length === 0) return null;

        // Optimization: For simple props, use instantiateHierarchy which is efficient
        const instance = masters[0].instantiateHierarchy(parent);
        if (instance) {
            instance.setEnabled(true);
            // Apply mesh-level optimizations to the instance
            instance.getChildMeshes().forEach(m => {
                m.freezeWorldMatrix();
                m.cullingStrategy = BABYLON.AbstractMesh.CULLINGSTRATEGY_BOUNDINGSPHERE_ONLY;
            });
        }
        return instance;
    }

    constructor(scene: BABYLON.Scene, data: BuildingData) {
        this.scene = scene;
        this.container = new BABYLON.Mesh("building-container", scene);
        this.create(data);
    }

    private create(data: BuildingData) {
        const { hits, is_public } = data;
        const level = hits < 10 ? 0 : (hits < 50 ? 1 : 2);

        // Use consistent textures from /static/assets/
        const facadeMat = new BABYLON.StandardMaterial("facade", this.scene);
        const tex = new BABYLON.Texture("/static/assets/cyber_facade.png", this.scene);
        facadeMat.diffuseTexture = tex;
        facadeMat.emissiveColor = new BABYLON.Color3(0.1, 0.1, 0.2);

        // Try to build with assets, otherwise use procedural fallback
        if (level === 0) {
            this.createCottage(facadeMat);
        } else if (level === 1) {
            this.createOffice(30, 60, 30, facadeMat);
        } else {
            this.createSkyscraper(40, 100, 40, facadeMat, is_public ? "#06b6d4" : "#a855f7");
        }

        this.createParcel();

        if (!data.isDeco) {
            this.addSign(data, 20);
            this.addHologramAd(60, 30);
            this.createInfoPanel(data, 80);
            this.container.metadata = { url: data.url };
        }
    }

    private addHologramAd(h: number, w: number) {
        const ad = BABYLON.MeshBuilder.CreatePlane("hologram", { width: 15, height: 10 }, this.scene);
        ad.position.set(w / 2 + 5, h * 0.7, 0);
        ad.rotation.y = Math.PI / 2;
        ad.parent = this.container;

        const adMat = new BABYLON.StandardMaterial("adMat", this.scene);
        adMat.diffuseTexture = new BABYLON.Texture("/static/assets/hologram_ad.png", this.scene);
        adMat.diffuseTexture.hasAlpha = true;
        adMat.emissiveColor = new BABYLON.Color3(0.5, 0.5, 1);
        adMat.alpha = 0.7;
        ad.material = adMat;

        this.scene.onBeforeRenderObservable.add(() => {
            ad.rotation.y += 0.01;
        });
    }

    private createParcel() {
        const parcelSize = 120;
        const parcel = BABYLON.MeshBuilder.CreateGround("parcel", { width: parcelSize, height: parcelSize }, this.scene);
        parcel.position.y = 0.05;
        parcel.parent = this.container;

        const parcelMat = new BABYLON.StandardMaterial("parcelMat", this.scene);
        parcelMat.diffuseTexture = new BABYLON.Texture("/static/assets/parking_lot.png", this.scene);
        parcel.material = parcelMat;
        parcel.checkCollisions = true;

        for (let i = 0; i < 4; i++) this.createCyberCar(parcelSize);
        for (let i = 0; i < 6; i++) this.createCyberTree(parcelSize);
    }

    private createCyberTree(parcelSize: number) {
        const x = (Math.random() - 0.5) * (parcelSize - 30);
        const z = (Math.random() - 0.5) * (parcelSize - 30);
        if (Math.abs(x) < 20 && Math.abs(z) < 20) return;

        if (Building.Assets.trees.length > 0) {
            const masters = Building.Assets.trees[0];
            const instance = masters[0].instantiateHierarchy(this.container);
            if (instance) {
                instance.position.set(x, 0, z);
                Building.applyNormalizedScale(instance, 18);
                instance.rotation.y = Math.random() * Math.PI;
                instance.setEnabled(true);
                return;
            }
        }

        // Simple procedural fallback
        const trunk = BABYLON.MeshBuilder.CreateCylinder("trunk", { height: 8, diameter: 0.5 }, this.scene);
        trunk.position.set(x, 4, z); trunk.parent = this.container;
        const leaves = BABYLON.MeshBuilder.CreateIcoSphere("leaves", { radius: 3 }, this.scene);
        leaves.position.set(x, 10, z); leaves.parent = this.container;
        const lMat = new BABYLON.StandardMaterial("lMat", this.scene);
        lMat.diffuseColor = new BABYLON.Color3(0.1, 0.4, 0.2);
        leaves.material = lMat;
    }

    private createCyberCar(parcelSize: number) {
        const x = (Math.random() - 0.5) * (parcelSize - 40);
        const z = (Math.random() - 0.5) * (parcelSize - 40);

        if (Building.Assets.cars.length > 0) {
            const idx = Math.floor(Math.random() * Building.Assets.cars.length);
            const instance = Building.Assets.cars[idx][0].instantiateHierarchy(this.container);
            if (instance) {
                instance.position.set(x, 0.5, z);
                Building.applyNormalizedScale(instance, 4);
                instance.rotation.y = Math.random() * Math.PI * 2;
                instance.setEnabled(true);
                return;
            }
        }

        const body = BABYLON.MeshBuilder.CreateBox("car", { width: 6, height: 1.5, depth: 3 }, this.scene);
        body.position.set(x, 1, z); body.parent = this.container;
    }

    private createCottage(mat: BABYLON.StandardMaterial) {
        if (Building.Assets.buildings.length > 0) {
            const idx = Math.floor(Math.random() * Math.min(Building.Assets.buildings.length, 2));
            const instance = Building.Assets.buildings[idx][0].instantiateHierarchy(this.container);
            if (instance) {
                Building.applyNormalizedScale(instance, 15);
                instance.rotation.y = Math.floor(Math.random() * 4) * (Math.PI / 2);
                instance.setEnabled(true);
                return;
            }
        }
        const box = BABYLON.MeshBuilder.CreateBox("cottage", { width: 20, height: 10, depth: 20 }, this.scene);
        box.position.y = 5; box.material = mat; box.parent = this.container;
    }

    private createOffice(w: number, h: number, d: number, mat: BABYLON.StandardMaterial) {
        if (Building.Assets.buildings.length > 2) {
            const idx = 1 + Math.floor(Math.random() * (Building.Assets.buildings.length - 2));
            const instance = Building.Assets.buildings[idx][0].instantiateHierarchy(this.container);
            if (instance) {
                Building.applyNormalizedScale(instance, 35);
                instance.rotation.y = Math.floor(Math.random() * 4) * (Math.PI / 2);
                instance.setEnabled(true);
                return;
            }
        }
        const box = BABYLON.MeshBuilder.CreateBox("office", { width: w, height: h, depth: d }, this.scene);
        box.position.y = h / 2; box.material = mat; box.parent = this.container;
    }

    private createSkyscraper(w: number, h: number, d: number, mat: BABYLON.StandardMaterial, color: string) {
        if (Building.Assets.buildings.length > 0) {
            const idx = Math.floor(Math.random() * Building.Assets.buildings.length);
            const instance = Building.Assets.buildings[idx][0].instantiateHierarchy(this.container);
            if (instance) {
                Building.applyNormalizedScale(instance, 60 + Math.random() * 40);
                instance.rotation.y = Math.floor(Math.random() * 4) * (Math.PI / 2);
                instance.setEnabled(true);
                return;
            }
        }
        const box = BABYLON.MeshBuilder.CreateBox("skyscraper", { width: w, height: h, depth: d }, this.scene);
        box.position.y = h / 2;
        box.material = mat;
        box.parent = this.container;

        // Use the color parameter for a glowy top or accent
        const top = BABYLON.MeshBuilder.CreateBox("sky-top", { width: w + 2, height: 2, depth: d + 2 }, this.scene);
        top.position.y = h;
        top.parent = box;

        const topMat = new BABYLON.StandardMaterial("topMat", this.scene);
        topMat.emissiveColor = BABYLON.Color3.FromHexString(color);
        top.material = topMat;
    }

    private addSign(data: BuildingData, depth: number) {
        const board = BABYLON.MeshBuilder.CreatePlane("board", { width: 8, height: 8 }, this.scene);
        board.position.set(0, 15, depth / 2 + 15);
        const bMat = new BABYLON.StandardMaterial("bMat", this.scene);
        bMat.diffuseTexture = new BABYLON.Texture(data.icon_url || '/favicon.svg', this.scene);
        bMat.diffuseTexture.hasAlpha = true;
        board.material = bMat;
        board.parent = this.container;
        board.billboardMode = BABYLON.Mesh.BILLBOARDMODE_ALL;
    }

    private createInfoPanel(data: BuildingData, h: number) {
        const plane = BABYLON.MeshBuilder.CreatePlane("info", { width: 14, height: 10 }, this.scene);
        plane.position.y = h + 15;
        plane.parent = this.container;
        plane.billboardMode = BABYLON.Mesh.BILLBOARDMODE_ALL;
        plane.isVisible = false;

        const ui = GUI.AdvancedDynamicTexture.CreateForMesh(plane, 512, 256);
        const rect = new GUI.Rectangle("info-panel-rect");
        rect.width = "480px"; rect.height = "220px"; rect.cornerRadius = 20;
        rect.background = "rgba(0,0,20,0.8)"; rect.color = "#00ffff"; rect.thickness = 4;
        ui.addControl(rect);

        const text = new GUI.TextBlock("info-panel-text");
        text.text = `${data.name}\n${data.hits} HITS`;
        text.color = "white"; text.fontSize = 40;
        rect.addControl(text);

        this.container.actionManager = new BABYLON.ActionManager(this.scene);
        this.container.actionManager.registerAction(new BABYLON.ExecuteCodeAction(BABYLON.ActionManager.OnPointerOverTrigger, () => plane.isVisible = true));
        this.container.actionManager.registerAction(new BABYLON.ExecuteCodeAction(BABYLON.ActionManager.OnPointerOutTrigger, () => plane.isVisible = false));
    }
}
