import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// Dual build entry (PLAY-FUSION-DECISIONS.md §二):
//   VITE_APP_TARGET=local (default) → dist-local: shared + play + local (study)
//   VITE_APP_TARGET=hub             → dist-hub:   shared + play + hub (storefront)
// Both share one index.html; the entry-target plugin swaps the script src so
// each dist tree-shakes the other product's pages out.
const target = process.env.VITE_APP_TARGET === 'hub' ? 'hub' : 'local'

export default defineConfig({
  server: { host: true },
  plugins: [
    react(),
    tailwindcss(),
    {
      name: 'worldlines-entry-target',
      // `pre` so the src is swapped BEFORE Vite resolves the module entry —
      // otherwise both builds keep index.html's default main-local.tsx.
      transformIndexHtml: {
        order: 'pre',
        handler(html: string) {
          return target === 'hub'
            ? html.replace('/src/main-local.tsx', '/src/main-hub.tsx')
            : html
        },
      },
    },
  ],
  build: { outDir: target === 'hub' ? 'dist-hub' : 'dist-local' },
})
