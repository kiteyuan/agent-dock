#!/usr/bin/env node
/**
 * Sticky Playwright MCP bridge.
 *
 * Public surface (default :8931) accepts ephemeral Pi MCP clients.
 * Internally one long-lived Client stays attached to Playwright MCP
 * (default :18931), so tab groups survive Pi's per-turn process exit.
 *
 * Admin mcp.json URL stays http://localhost:8931/mcp — no config change.
 */
import { spawn } from "node:child_process";
import { randomUUID } from "node:crypto";
import { setTimeout as delay } from "node:timers/promises";

import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StreamableHTTPClientTransport } from "@modelcontextprotocol/sdk/client/streamableHttp.js";
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/streamableHttp.js";
import { createMcpExpressApp } from "@modelcontextprotocol/sdk/server/express.js";
import {
  CallToolRequestSchema,
  GetPromptRequestSchema,
  isInitializeRequest,
  ListPromptsRequestSchema,
  ListResourcesRequestSchema,
  ListResourceTemplatesRequestSchema,
  ListToolsRequestSchema,
  ReadResourceRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";

const PUBLIC_HOST = process.env.PUBLIC_HOST || "127.0.0.1";
const PUBLIC_PORT = Number(process.env.PUBLIC_PORT || process.env.PORT || 8931);
const INTERNAL_HOST = process.env.INTERNAL_HOST || "127.0.0.1";
const INTERNAL_PORT = Number(process.env.INTERNAL_PORT || 18931);
// Playwright MCP host-checks the literal hostname "localhost".
const UPSTREAM_URL =
  process.env.UPSTREAM_URL || `http://localhost:${INTERNAL_PORT}/mcp`;
const UPSTREAM_PROBE_HOST = process.env.UPSTREAM_PROBE_HOST || INTERNAL_HOST;

const log = (...args) => console.error("[playwright-bridge]", ...args);

let upstreamChild = null;
let stickyClient = null;
let stickyTransport = null;
let connecting = null;
const sessions = new Map();

function createProxyServer(upstream) {
  const caps = upstream.getServerCapabilities() || { tools: {} };
  const version = upstream.getServerVersion();
  const server = new Server(
    {
      name: "agentdock-playwright-bridge",
      version: "1.0.0",
      ...(version?.title ? { title: version.title } : {}),
    },
    {
      capabilities: caps,
      ...(upstream.getInstructions()
        ? { instructions: upstream.getInstructions() }
        : {}),
    },
  );

  if (caps.tools) {
    server.setRequestHandler(ListToolsRequestSchema, async () =>
      upstream.listTools(),
    );
    server.setRequestHandler(CallToolRequestSchema, async (request) =>
      upstream.callTool(request.params),
    );
  }
  if (caps.resources) {
    server.setRequestHandler(ListResourcesRequestSchema, async (request) =>
      upstream.listResources(request.params),
    );
    server.setRequestHandler(ListResourceTemplatesRequestSchema, async (request) =>
      upstream.listResourceTemplates(request.params),
    );
    server.setRequestHandler(ReadResourceRequestSchema, async (request) =>
      upstream.readResource(request.params),
    );
  }
  if (caps.prompts) {
    server.setRequestHandler(ListPromptsRequestSchema, async (request) =>
      upstream.listPrompts(request.params),
    );
    server.setRequestHandler(GetPromptRequestSchema, async (request) =>
      upstream.getPrompt(request.params),
    );
  }
  return server;
}

async function probeTcp(host, port) {
  const net = await import("node:net");
  return new Promise((resolve) => {
    const sock = new net.Socket();
    const done = (v) => {
      sock.destroy();
      resolve(v);
    };
    sock.setTimeout(800);
    sock.once("connect", () => done(true));
    sock.once("timeout", () => done(false));
    sock.once("error", () => done(false));
    sock.connect(port, host);
  });
}

async function waitForPort(host, port, timeoutMs = 90_000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (await probeTcp(host, port)) return;
    await delay(400);
  }
  throw new Error(`upstream ${host}:${port} did not accept TCP within ${timeoutMs}ms`);
}

function spawnUpstream() {
  if (process.env.SKIP_SPAWN_UPSTREAM === "1") {
    log("SKIP_SPAWN_UPSTREAM=1 — expecting existing Playwright at", UPSTREAM_URL);
    return;
  }
  const npx = process.env.NPX_PATH || (process.platform === "win32" ? "npx.cmd" : "npx");
  const args = [
    "-y",
    "@playwright/mcp@latest",
    "--extension",
    "--caps",
    "vision",
    "--host",
    INTERNAL_HOST,
    "--port",
    String(INTERNAL_PORT),
  ];
  log("spawning Playwright MCP:", npx, args.join(" "));
  upstreamChild = spawn(npx, args, {
    env: process.env,
    stdio: ["ignore", "inherit", "inherit"],
    shell: process.platform === "win32",
    windowsHide: true,
  });
  upstreamChild.on("exit", (code, signal) => {
    log(`Playwright MCP exited code=${code} signal=${signal}`);
    upstreamChild = null;
    stickyClient = null;
    stickyTransport = null;
  });
}

async function connectSticky() {
  if (stickyClient) return stickyClient;
  if (connecting) return connecting;
  connecting = (async () => {
    await waitForPort(UPSTREAM_PROBE_HOST, INTERNAL_PORT);
    log("connecting sticky client →", UPSTREAM_URL);
    const transport = new StreamableHTTPClientTransport(new URL(UPSTREAM_URL));
    const client = new Client({
      name: "agentdock-playwright-sticky",
      version: "1.0.0",
    });
    await client.connect(transport);
    stickyTransport = transport;
    stickyClient = client;
    log(
      "sticky session ready; tools capability=",
      Boolean(client.getServerCapabilities()?.tools),
    );
    return client;
  })()
    .catch((err) => {
      stickyClient = null;
      stickyTransport = null;
      throw err;
    })
    .finally(() => {
      connecting = null;
    });
  return connecting;
}

async function ensureSticky() {
  try {
    if (stickyClient) {
      // cheap liveness: listTools; reconnect on failure
      await stickyClient.listTools();
      return stickyClient;
    }
  } catch (err) {
    log("sticky client stale, reconnecting:", err?.message || err);
    try {
      await stickyClient?.close();
    } catch {
      /* ignore */
    }
    stickyClient = null;
    stickyTransport = null;
  }
  return connectSticky();
}

function dropSession(sessionId, transport) {
  if (sessionId && sessions.get(sessionId) === transport) {
    sessions.delete(sessionId);
    log("dropped downstream session", sessionId);
  }
}

async function handleMcpPost(req, res) {
  const sessionId = req.headers["mcp-session-id"];
  try {
    await ensureSticky();
    let transport;
    if (sessionId && sessions.has(sessionId)) {
      transport = sessions.get(sessionId);
    } else if (!sessionId && isInitializeRequest(req.body)) {
      transport = new StreamableHTTPServerTransport({
        sessionIdGenerator: () => randomUUID(),
        onsessioninitialized: (sid) => {
          sessions.set(sid, transport);
          log("downstream session", sid);
        },
      });
      transport.onclose = () => dropSession(transport.sessionId, transport);
      const proxy = createProxyServer(stickyClient);
      await proxy.connect(transport);
      await transport.handleRequest(req, res, req.body);
      return;
    } else {
      res.status(400).json({
        jsonrpc: "2.0",
        error: {
          code: -32000,
          message: "Bad Request: No valid session ID provided",
        },
        id: null,
      });
      return;
    }
    await transport.handleRequest(req, res, req.body);
  } catch (err) {
    log("POST /mcp error:", err?.message || err);
    if (!res.headersSent) {
      res.status(500).json({
        jsonrpc: "2.0",
        error: { code: -32603, message: "Internal server error" },
        id: null,
      });
    }
  }
}

async function handleMcpGet(req, res) {
  const sessionId = req.headers["mcp-session-id"];
  if (!sessionId || !sessions.has(sessionId)) {
    res.status(400).send("Invalid or missing session ID");
    return;
  }
  await sessions.get(sessionId).handleRequest(req, res);
}

async function handleMcpDelete(req, res) {
  const sessionId = req.headers["mcp-session-id"];
  if (!sessionId || !sessions.has(sessionId)) {
    res.status(400).send("Invalid or missing session ID");
    return;
  }
  const transport = sessions.get(sessionId);
  await transport.handleRequest(req, res);
  dropSession(sessionId, transport);
}

async function shutdown(signal) {
  log("shutdown", signal);
  for (const [sid, transport] of sessions) {
    try {
      await transport.close();
    } catch {
      /* ignore */
    }
    sessions.delete(sid);
  }
  try {
    await stickyClient?.close();
  } catch {
    /* ignore */
  }
  stickyClient = null;
  if (upstreamChild && !upstreamChild.killed) {
    try {
      if (process.platform === "win32") {
        spawn("taskkill", ["/PID", String(upstreamChild.pid), "/T", "/F"], {
          stdio: "ignore",
          windowsHide: true,
        });
      } else {
        upstreamChild.kill("SIGTERM");
      }
    } catch {
      /* ignore */
    }
  }
  process.exit(0);
}

async function main() {
  spawnUpstream();
  await connectSticky();

  const app = createMcpExpressApp({
    host: PUBLIC_HOST,
    allowedHosts: ["127.0.0.1", "localhost", "[::1]"],
  });

  app.post("/mcp", (req, res) => void handleMcpPost(req, res));
  app.get("/mcp", (req, res) => void handleMcpGet(req, res));
  app.delete("/mcp", (req, res) => void handleMcpDelete(req, res));
  app.get("/healthz", (_req, res) => {
    res.json({
      ok: Boolean(stickyClient),
      public: `${PUBLIC_HOST}:${PUBLIC_PORT}`,
      upstream: UPSTREAM_URL,
      sessions: sessions.size,
    });
  });

  await new Promise((resolve, reject) => {
    const server = app.listen(PUBLIC_PORT, PUBLIC_HOST, () => {
      log(`listening http://${PUBLIC_HOST}:${PUBLIC_PORT}/mcp → ${UPSTREAM_URL}`);
      resolve(server);
    });
    server.on("error", reject);
  });

  process.on("SIGINT", () => void shutdown("SIGINT"));
  process.on("SIGTERM", () => void shutdown("SIGTERM"));
}

main().catch((err) => {
  console.error("[playwright-bridge] fatal:", err);
  process.exit(1);
});
