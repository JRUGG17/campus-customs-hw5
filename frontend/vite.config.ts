import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// The page runs on http://localhost:5173 and calls the FastAPI backend at http://localhost:8000.
// The backend allows that origin (CORS), so the browser may call it directly. strictPort keeps
// the page on 5173: if the port is taken, Vite stops instead of moving to a port the backend
// doesn't allow.
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, strictPort: true },
})
