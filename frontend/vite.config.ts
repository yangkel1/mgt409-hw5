import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// The dashboard runs on http://localhost:5173 and talks to the FastAPI backend
// at http://localhost:8000 (override with VITE_API_BASE). The backend's CORS
// settings allow this origin.
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, strictPort: true },
})
