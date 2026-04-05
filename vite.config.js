import { defineConfig } from 'vite';
import { resolve } from 'path';

export default defineConfig({
    build: {
        outDir: 'static/3d-dist',
        emptyOutDir: true,
        lib: {
            entry: resolve(__dirname, 'src-3d/main.ts'),
            name: 'MagicHub3D',
            formats: ['iife'],
            fileName: () => 'bundle.js'
        },
        rollupOptions: {
            output: {
                extend: true
            }
        }
    },
    resolve: {
        alias: {
            '@': resolve(__dirname, 'src-3d'),
        },
    },
});
