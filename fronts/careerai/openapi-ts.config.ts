// Generates lib/client (types.gen.ts, sdk.gen.ts and the shared client in client.gen.ts)
// from openapi.json, FastAPI's spec of apis/schemas.py. Regenerate with `just gen-api`
// after a backend change; never edit lib/client by hand.
import { defineConfig } from "@hey-api/openapi-ts"

export default defineConfig({
  input: "./openapi.json",
  output: "lib/client",
  plugins: [
    "@hey-api/typescript",
    "@hey-api/sdk",
    // lib/hey-api.ts sets baseUrl at runtime from NEXT_PUBLIC_API_URL.
    { name: "@hey-api/client-fetch", runtimeConfigPath: "@/lib/hey-api" },
  ],
})
