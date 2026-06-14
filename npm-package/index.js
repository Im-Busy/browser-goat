#!/usr/bin/env node

/**
 * browsing-meta MCP server wrapper.
 *
 * Spawns the Python `browsing-meta-mcp` CLI as a subprocess and proxies
 * stdin/stdout for MCP stdio transport. The npm package itself contains
 * no logic — it's a thin bridge to the Python backend.
 *
 * Usage:
 *   npx browsing-meta
 *   SEARXNG_URL=http://localhost:8080 npx browsing-meta
 */

const { spawn } = require("child_process");

const searxngUrl = process.env.SEARXNG_URL || "http://localhost:8080";

const args = ["-m", "browsing_meta.mcp_server", "--searxng-url", searxngUrl];
const pythonCmd = process.env.PYTHON_CMD || "python";

const child = spawn(pythonCmd, args, {
  stdio: ["pipe", "pipe", "pipe"],
  env: { ...process.env },
});

// Proxy stdin → child
process.stdin.pipe(child.stdin);

// Proxy child stdout → stdout
child.stdout.pipe(process.stdout);

// Proxy child stderr → stderr (for logging)
child.stderr.pipe(process.stderr);

child.on("error", (err) => {
  console.error(`[browsing-meta] Failed to start Python backend: ${err.message}`);
  console.error(`[browsing-meta] Ensure browsing-meta is installed: pip install browsing-meta`);
  process.exit(1);
});

child.on("exit", (code) => {
  process.exit(code || 0);
});

// Forward signals
process.on("SIGTERM", () => child.kill("SIGTERM"));
process.on("SIGINT", () => child.kill("SIGINT"));
