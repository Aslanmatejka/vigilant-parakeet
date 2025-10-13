import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

export default defineConfig(({ mode }) => {
  // Load env file based on `mode` in the current working directory.
  const env = loadEnv(mode, process.cwd(), '');
  
  return {
    plugins: [react()],
    root: '.',
    build: {
      outDir: 'dist',
      rollupOptions: {
        input: {
          main: path.resolve(__dirname, 'index.html')
        }
      }
    },
    server: {
      port: env.PORT || 3001,
      open: true,
      historyApiFallback: true
    },
    resolve: {
      alias: {
        '@': path.resolve(__dirname, './')
      }
    },
    define: {
      'process.env': env
    }
  };
}); 