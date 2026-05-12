import { defineConfig, type Plugin } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'
import { promises as fs } from 'fs'
import { brotliCompress, constants, gzip } from 'zlib'
import { promisify } from 'util'

const gzipAsync = promisify(gzip)
const brotliAsync = promisify(brotliCompress)
const compressedExtensions = new Set(['.js', '.mjs', '.json', '.css', '.html'])
const compressionThresholdBytes = 1024

async function listFiles(root: string): Promise<string[]> {
  const entries = await fs.readdir(root, { withFileTypes: true })
  const nested = await Promise.all(
    entries.map(async (entry) => {
      const fullPath = path.join(root, entry.name)
      if (entry.isDirectory()) {
        return listFiles(fullPath)
      }
      return entry.isFile() ? [fullPath] : []
    }),
  )

  return nested.flat()
}

function staticCompression(): Plugin {
  let outputPath = ''

  return {
    name: 'marketing-bot-static-compression',
    apply: 'build',
    enforce: 'post',
    configResolved(config) {
      outputPath = path.isAbsolute(config.build.outDir)
        ? config.build.outDir
        : path.resolve(config.root, config.build.outDir)
    },
    async closeBundle() {
      const files = await listFiles(outputPath)
      const targets = []

      for (const filePath of files) {
        if (filePath.endsWith('.gz') || filePath.endsWith('.br')) {
          continue
        }
        if (!compressedExtensions.has(path.extname(filePath).toLowerCase())) {
          continue
        }

        const stats = await fs.stat(filePath)
        if (stats.size >= compressionThresholdBytes) {
          targets.push(filePath)
        }
      }

      await Promise.all(
        targets.map(async (filePath) => {
          const source = await fs.readFile(filePath)
          const [gzipped, brotli] = await Promise.all([
            gzipAsync(source, { level: constants.Z_BEST_COMPRESSION }),
            brotliAsync(source, {
              params: {
                [constants.BROTLI_PARAM_QUALITY]: constants.BROTLI_MAX_QUALITY,
                [constants.BROTLI_PARAM_MODE]: constants.BROTLI_MODE_TEXT,
              },
            }),
          ])

          await Promise.all([
            fs.writeFile(`${filePath}.gz`, gzipped),
            fs.writeFile(`${filePath}.br`, brotli),
          ])
        }),
      )

      console.info(`static compression: wrote gzip and brotli for ${targets.length} files`)
    },
  }
}

export default defineConfig({
  plugins: [
    react(),
    staticCompression(),
  ],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    host: true,
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true,
      },
    },
  },
  build: {
    target: 'esnext',
    minify: 'oxc',
    sourcemap: false,
    chunkSizeWarningLimit: 1000,
    cssCodeSplit: true,
  },
  optimizeDeps: {
    include: ['react', 'react-dom', 'react-router-dom', '@tanstack/react-query'],
  },
})
