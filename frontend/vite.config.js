import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'
import tailwindcss from "@tailwindcss/vite"

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  // Reads the repo-root .env the backend also uses (then frontend/.env*, then the shell),
  // so moving the backend with SERVER_PORT moves the /api proxy with it.
  const env = { ...loadEnv(mode, '..', ''), ...loadEnv(mode, '.', '') }

  return {
    plugins: [react(), tailwindcss()],
    server: {
      port: Number(env.FRONTEND_PORT) || 5173,
      // A pinned port is what a reverse proxy points at, so fail instead of drifting to the next one.
      strictPort: Boolean(env.FRONTEND_PORT),
      allowedHosts: ['staging.faflist.solutions', 'staging2.faflist.solutions'],
      proxy: {
        '/api': env.API_PROXY_TARGET || `http://localhost:${env.SERVER_PORT || 8081}`,
      },
    },
  }
})
