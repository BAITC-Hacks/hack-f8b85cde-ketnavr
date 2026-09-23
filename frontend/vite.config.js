import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  const localOnly = mode === 'localhost';
  return {
    plugins: [react()],
    // Explicit local mode cannot inherit an old tunnel URL or demo setting.
    ...(localOnly ? { define: {
      'import.meta.env.VITE_API_BASE_URL': JSON.stringify('/api'),
      'import.meta.env.VITE_RECOMMENDATIONS_PATH': JSON.stringify('/recommendations?ai=false&limit=0'),
      'import.meta.env.VITE_DATA_MODE': JSON.stringify('api'),
    } } : {}),
    server: {
      port: 5173,
      strictPort: true,
      proxy: {
        '/api': {
          target: localOnly ? 'http://127.0.0.1:8000' : env.BACKEND_URL || 'http://127.0.0.1:8000',
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/api(?=\/|$)/, ''),
        },
      },
    },
    build: { target: 'es2022' },
  };
});

