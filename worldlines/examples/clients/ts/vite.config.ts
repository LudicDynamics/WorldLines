// The page talks to the host through Vite's dev proxy: same origin, so no CORS, and the token rides in a normal header.
//   WL_HOST=http://127.0.0.1:8788 npm run dev
import { defineConfig } from 'vite'

const target = process.env.WL_HOST || 'http://127.0.0.1:8788'

export default defineConfig({
  publicDir: '../art',   // the world art packs (examples/clients/art/<world>/) are served at /<world>/…
  server: {
    port: 5180,
    proxy: {
      '/rpc': { target, changeOrigin: true },
      '/api': { target, changeOrigin: true },
      '/state': { target, changeOrigin: true },
    },
  },
})
