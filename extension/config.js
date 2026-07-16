// GOOPHER extension configuration.
// Point API_BASE at your backend: a local dev server (default) or your own
// deployed Cloud Run service.
export const CONFIG = {
  // Local backend (default — works out of the box with `uvicorn backend.app.main:app`):
  API_BASE: "http://localhost:8080",
  // Deployed Cloud Run service (ADK + Gemini on Vertex AI). Replace with the URL
  // printed by your own deploy, then reload the extension:
  // API_BASE: "https://<your-service>-<hash>-<region>.a.run.app",
};
