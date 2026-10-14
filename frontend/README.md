# AML Transaction Monitoring frontend

This React + TypeScript application is the Phase 3.2 shell only. It uses Vite
for local development and keeps the FastAPI backend as the only API server.

## Local development

1. Start the FastAPI application from the project root using the existing
   backend instructions.
2. Copy `.env.example` to `.env` if the backend is not at
   `http://127.0.0.1:8000`.
3. Run `npm install`, then `npm run dev` from `frontend/`.

The API client reads `VITE_API_BASE_URL`; it does not contain credentials or
hard-coded application data. During Vite development, `/api` is proxied to the
local FastAPI server to avoid requiring backend CORS changes. Set the variable
to the deployed API origin when hosting the frontend separately.
