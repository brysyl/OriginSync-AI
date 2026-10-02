import { cp, mkdir } from "node:fs/promises";

await cp("public", ".next/standalone/public", { recursive: true });
await mkdir(".next/standalone/.next", { recursive: true });
await cp(".next/static", ".next/standalone/.next/static", { recursive: true });
