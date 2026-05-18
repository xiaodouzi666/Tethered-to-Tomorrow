import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('.', import.meta.url));

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173
  },
  build: {
    rollupOptions: {
      input: {
        main: `${root}index.html`,
        openmct: `${root}openmct.html`,
        twin: `${root}twin.html`
      }
    }
  }
});
