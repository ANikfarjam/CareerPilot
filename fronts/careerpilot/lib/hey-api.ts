// Runtime config for the shared client in lib/client/client.gen.ts (see openapi-ts.config.ts).
import type { CreateClientConfig } from "./client/client.gen"

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"

export const createClientConfig: CreateClientConfig = (config) => ({ ...config, baseUrl: API_URL })
