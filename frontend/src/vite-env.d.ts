/// <reference types="vite/client" />

interface ImportMetaEnv {
  /**
   * Backend API base URL such as "http://localhost:8000". Unset or empty
   * means the API is served from the same origin as the frontend.
   */
  readonly VITE_API_BASE_URL?: string
  /**
   * Development mock adapter opt-in. Only the exact string "true" enables
   * labeled ("Sample data") fixtures; see `src/mocks/index.ts`.
   */
  readonly VITE_USE_MOCKS?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
