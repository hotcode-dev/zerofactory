import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  plugins: [
    react({
      jsxRuntime: 'classic',
    }),
  ],
  resolve: {
    alias: {
      react: path.resolve(__dirname, 'dashboard/src/react-shim.js'),
    },
  },
  build: {
    outDir: path.resolve(__dirname, 'dashboard/dist'),
    emptyOutDir: false,
    lib: {
      entry: path.resolve(__dirname, 'dashboard/src/index.js'),
      name: 'ZeroFactoryDashboard',
      formats: ['iife'],
      fileName: () => 'index.js',
    },
    minify: false,
  },
});
