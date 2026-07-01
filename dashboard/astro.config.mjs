// @ts-check
import { defineConfig } from 'astro/config';

// https://astro.build/config
export default defineConfig({
  vite: {
    server: {
      allowedHosts: ['pi.ntsd.dev'],
      proxy: {
        '/api': {
          target: 'http://localhost:18780',
          changeOrigin: true
        }
      }
    }
  }
});
