import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
export default defineConfig({plugins:[react(),tailwindcss()],build:{outDir:'../swarmcompute/static',emptyOutDir:true,rollupOptions:{output:{manualChunks:{charts:['recharts'],react:['react','react-dom','react-router-dom']}}}},server:{proxy:{'/api':'http://localhost:8787','/health':'http://localhost:8787'}}})
