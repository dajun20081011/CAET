import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'node:path'

// 本地开发后端端口（与生产 .env 的 PORT 保持一致，可用环境变量覆盖）
const DEV_API_PORT = process.env.CAET_DEV_API_PORT || '8000'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': resolve(import.meta.dirname, 'src'),
    },
  },
  server: {
    port: 3000,
    host: true,
    // 本地开发代理：前端 /api、/uploads 转发到 FastAPI（默认 8100，可用 CAET_DEV_API_PORT 覆盖），与生产 Nginx 行为一致
    proxy: {
      '/api': { target: `http://127.0.0.1:${DEV_API_PORT}`, changeOrigin: true },
      '/uploads': { target: `http://127.0.0.1:${DEV_API_PORT}`, changeOrigin: true },
      '/media': { target: `http://127.0.0.1:${DEV_API_PORT}`, changeOrigin: true },
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    sourcemap: false,
    // 拆分 element-plus 等大依赖，提升首屏加载
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes('element-plus') || id.includes('@element-plus/icons-vue')) return 'element-plus'
          if (id.includes('node_modules/vue') || id.includes('vue-router') || id.includes('pinia')) return 'vendor'
        },
      },
    },
  },
})
