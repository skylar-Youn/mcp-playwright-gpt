// server.mjs
import { chromium, request as pwRequest } from "playwright";
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";

/**
 * Design:
 * - Single browser (Chromium)
 * - Multiple contexts (to vary UA/locale/viewport/permissions)
 * - Multiple pages; each page belongs to a context
 * - Track currentPageId for convenience
 */

let browser;
let ctxCounter = 0;
let pageCounter = 0;
let currentPageId = null;

const contexts = new Map(); // contextId -> BrowserContext
const pages = new Map();    // pageId -> { page, contextId }

function newId(prefix, counterFn) {
  return `${prefix}_${counterFn()}`;
}

// counters
const nextCtx = () => ++ctxCounter;
const nextPage = () => ++pageCounter;

async function ensureBrowser() {
  if (!browser) {
    console.log("[MCP-Playwright] Launching Chromium...");
    browser = await chromium.launch({ headless: true });
    console.log("[MCP-Playwright] Browser launched.");
  }
  return browser;
}

async function createContext(options = {}) {
  await ensureBrowser();

  const {
    userAgent,
    viewport,            // { width, height }
    locale,
    geolocation,         // { latitude, longitude, accuracy }
    permissions,         // string[] (e.g. ['geolocation'])
    httpCredentials,     // { username, password }
    timezoneId,
    proxy,               // { server, username, password }
    extraHTTPHeaders,    // object map
    colorScheme          // 'light' | 'dark' | 'no-preference'
  } = options;

  const context = await browser.newContext({
    userAgent,
    viewport,
    locale,
    geolocation,
    permissions,
    httpCredentials,
    timezoneId,
    proxy,
    colorScheme,
    extraHTTPHeaders,
  });

  const contextId = newId("ctx", nextCtx);
  contexts.set(contextId, context);
  console.log(`[MCP-Playwright] Created context: ${contextId}`);
  return contextId;
}

async function createPage(contextId) {
  if (!contexts.has(contextId)) {
    throw new Error(`Unknown contextId: ${contextId}`);
  }
  const context = contexts.get(contextId);
  const page = await context.newPage();
  const pageId = newId("page", nextPage);
  pages.set(pageId, { page, contextId });
  currentPageId = pageId;
  console.log(`[MCP-Playwright] Created page: ${pageId} (context: ${contextId})`);
  return pageId;
}

function getPageOrThrow(pageId) {
  const id = pageId || currentPageId;
  if (!id) throw new Error("No active page. Create one with newContext + newPage or pass pageId.");
  const entry = pages.get(id);
  if (!entry) throw new Error(`Unknown pageId: ${id}`);
  return { pageId: id, ...entry };
}

async function closePage(pageId) {
  const entryId = pageId || currentPageId;
  if (!entryId) return;
  const entry = pages.get(entryId);
  if (entry) {
    await entry.page.close().catch(() => {});
    pages.delete(entryId);
    if (currentPageId === entryId) currentPageId = null;
    console.log(`[MCP-Playwright] Closed page: ${entryId}`);
  }
}

async function closeContext(contextId) {
  if (!contexts.has(contextId)) return;
  // Close all pages belonging to this context
  for (const [pid, { contextId: cid }] of pages.entries()) {
    if (cid === contextId) {
      await closePage(pid);
    }
  }
  const ctx = contexts.get(contextId);
  await ctx.close().catch(() => {});
  contexts.delete(contextId);
  console.log(`[MCP-Playwright] Closed context: ${contextId}`);
}

async function resetAll() {
  for (const ctxId of Array.from(contexts.keys())) {
    await closeContext(ctxId);
  }
  if (browser) {
    await browser.close().catch(() => {});
    browser = null;
  }
  console.log("[MCP-Playwright] Reset all (browser, contexts, pages).");
}

// ---- MCP Server ----
const server = new Server(
  { name: "mcp-playwright", version: "1.0.0" },
  {
    tools: [
      // Lifecycle / Management
      {
        name: "reset",
        description: "Close everything (browser, contexts, pages).",
        inputSchema: { type: "object", properties: {} }
      },
      {
        name: "newContext",
        description: "Create a new browser context with options.",
        inputSchema: {
          type: "object",
          properties: {
            userAgent: { type: "string" },
            viewport: {
              type: "object",
              properties: { width: { type: "number" }, height: { type: "number" } },
            },
            locale: { type: "string" },
            geolocation: {
              type: "object",
              properties: {
                latitude: { type: "number" },
                longitude: { type: "number" },
                accuracy: { type: "number" }
              }
            },
            permissions: { type: "array", items: { type: "string" } },
            httpCredentials: {
              type: "object",
              properties: { username: { type: "string" }, password: { type: "string" } }
            },
            timezoneId: { type: "string" },
            proxy: {
              type: "object",
              properties: { server: { type: "string" }, username: { type: "string" }, password: { type: "string" } }
            },
            extraHTTPHeaders: { type: "object" },
            colorScheme: { type: "string" }
          }
        }
      },
      {
        name: "newPage",
        description: "Create a new page in the given context.",
        inputSchema: {
          type: "object",
          properties: { contextId: { type: "string" } },
          required: ["contextId"]
        }
      },
      {
        name: "switchPage",
        description: "Switch current active page by pageId.",
        inputSchema: {
          type: "object",
          properties: { pageId: { type: "string" } },
          required: ["pageId"]
        }
      },
      {
        name: "closePage",
        description: "Close a page (defaults to current if omitted).",
        inputSchema: {
          type: "object",
          properties: { pageId: { type: "string" } }
        }
      },
      {
        name: "closeContext",
        description: "Close a context and its pages.",
        inputSchema: {
          type: "object",
          properties: { contextId: { type: "string" } },
          required: ["contextId"]
        }
      },

      // Navigation / DOM
      {
        name: "open",
        description: "Open URL on a page.",
        inputSchema: {
          type: "object",
          properties: {
            url: { type: "string" },
            pageId: { type: "string" },
            waitUntil: { type: "string" } // 'load' | 'domcontentloaded' | 'networkidle'
          },
          required: ["url"]
        }
      },
      {
        name: "waitFor",
        description: "Wait for selector to appear (or reach state).",
        inputSchema: {
          type: "object",
          properties: {
            selector: { type: "string" },
            timeoutMs: { type: "number" },
            state: { type: "string" } // 'attached' | 'detached' | 'visible' | 'hidden'
          },
          required: ["selector"]
        }
      },
      {
        name: "waitForNavigation",
        description: "Wait for page navigation.",
        inputSchema: {
          type: "object",
          properties: {
            timeoutMs: { type: "number" },
            waitUntil: { type: "string" } // 'load' | 'domcontentloaded' | 'networkidle'
          }
        }
      },
      { // clicks
        name: "click",
        description: "Click a selector.",
        inputSchema: {
          type: "object",
          properties: { selector: { type: "string" }, pageId: { type: "string" } },
          required: ["selector"]
        }
      },
      {
        name: "clickNth",
        description: "Click the Nth matching element (0-based).",
        inputSchema: {
          type: "object",
          properties: {
            selector: { type: "string" },
            index: { type: "number" },
            pageId: { type: "string" }
          },
          required: ["selector", "index"]
        }
      },

      // Input
      {
        name: "fill",
        description: "Fill input/textarea.",
        inputSchema: {
          type: "object",
          properties: {
            selector: { type: "string" },
            text: { type: "string" },
            pageId: { type: "string" }
          },
          required: ["selector", "text"]
        }
      },
      {
        name: "type",
        description: "Type into a selector (keystroke-level, supports delay).",
        inputSchema: {
          type: "object",
          properties: {
            selector: { type: "string" },
            text: { type: "string" },
            delayMs: { type: "number" },
            pageId: { type: "string" }
          },
          required: ["selector", "text"]
        }
      },
      {
        name: "press",
        description: "Press a keyboard key (e.g. Enter, Tab, ArrowDown).",
        inputSchema: {
          type: "object",
          properties: { key: { type: "string" }, pageId: { type: "string" } },
          required: ["key"]
        }
      },

      // Extract / Evaluate
      {
        name: "getText",
        description: "Get innerText of first matching element.",
        inputSchema: {
          type: "object",
          properties: { selector: { type: "string" }, pageId: { type: "string" } },
          required: ["selector"]
        }
      },
      {
        name: "eval",
        description: "Evaluate JS in page context and return result as JSON.",
        inputSchema: {
          type: "object",
          properties: {
            expression: { type: "string" },
            pageId: { type: "string" }
          },
          required: ["expression"]
        }
      },

      // Screenshot / Download
      {
        name: "screenshot",
        description: "Capture PNG screenshot, optionally save.",
        inputSchema: {
          type: "object",
          properties: {
            path: { type: "string" },
            fullPage: { type: "boolean" },
            pageId: { type: "string" }
          }
        }
      },
      {
        name: "download",
        description: "Download a file either by clicking a selector or direct URL.",
        inputSchema: {
          type: "object",
          properties: {
            mode: { type: "string" },       // 'click' | 'url'
            selector: { type: "string" },   // required if mode='click'
            url: { type: "string" },        // required if mode='url'
            path: { type: "string" },
            pageId: { type: "string" }
          },
          required: ["mode", "path"]
        }
      },

      // HTTP Request (out of page)
      {
        name: "request",
        description: "HTTP request via Playwright's request context (GET/POST/etc).",
        inputSchema: {
          type: "object",
          properties: {
            method: { type: "string" }, // GET, POST, PUT, DELETE
            url: { type: "string" },
            headers: { type: "object" },
            data: { type: "object" },
            timeoutMs: { type: "number" }
          },
          required: ["method", "url"]
        }
      }
    ]
  }
);

server.setRequestHandler("tools/call", async (req) => {
  const { name, arguments: args } = req.params;
  console.log(`[MCP-Playwright] Tool call: ${name}`, args);

  try {
    // Lifecycle
    if (name === "reset") {
      await resetAll();
      return { content: [{ type: "text", text: "Reset OK" }] };
    }

    if (name === "newContext") {
      const ctxId = await createContext(args);
      // create default page for convenience
      const pageId = await createPage(ctxId);
      return { content: [{ type: "text", text: JSON.stringify({ contextId: ctxId, pageId }) }] };
    }

    if (name === "newPage") {
      const pageId = await createPage(args.contextId);
      return { content: [{ type: "text", text: JSON.stringify({ pageId }) }] };
    }

    if (name === "switchPage") {
      if (!pages.has(args.pageId)) throw new Error(`Unknown pageId: ${args.pageId}`);
      currentPageId = args.pageId;
      return { content: [{ type: "text", text: `Switched to ${args.pageId}` }] };
    }

    if (name === "closePage") {
      await closePage(args.pageId);
      return { content: [{ type: "text", text: "Page closed" }] };
    }

    if (name === "closeContext") {
      await closeContext(args.contextId);
      return { content: [{ type: "text", text: "Context closed" }] };
    }

    // Navigation / DOM
    if (name === "open") {
      const { page } = getPageOrThrow(args.pageId);
      await page.goto(args.url, { waitUntil: args.waitUntil || "load" });
      return { content: [{ type: "text", text: `Opened ${args.url}` }] };
    }

    if (name === "waitFor") {
      const { page } = getPageOrThrow(args.pageId);
      await page.waitForSelector(args.selector, {
        timeout: args.timeoutMs ?? 15000,
        state: args.state || "attached"
      });
      return { content: [{ type: "text", text: `Selector ready: ${args.selector}` }] };
    }

    if (name === "waitForNavigation") {
      const { page } = getPageOrThrow(args.pageId);
      await page.waitForLoadState(args.waitUntil || "load", { timeout: args.timeoutMs ?? 30000 });
      return { content: [{ type: "text", text: `Navigation complete (${args.waitUntil || "load"})` }] };
    }

    if (name === "click") {
      const { page } = getPageOrThrow(args.pageId);
      await page.click(args.selector);
      return { content: [{ type: "text", text: `Clicked ${args.selector}` }] };
    }

    if (name === "clickNth") {
      const { page } = getPageOrThrow(args.pageId);
      const loc = page.locator(args.selector).nth(args.index);
      await loc.click();
      return { content: [{ type: "text", text: `Clicked ${args.selector}[${args.index}]` }] };
    }

    // Input
    if (name === "fill") {
      const { page } = getPageOrThrow(args.pageId);
      await page.fill(args.selector, args.text);
      return { content: [{ type: "text", text: `Filled ${args.selector}` }] };
    }

    if (name === "type") {
      const { page } = getPageOrThrow(args.pageId);
      await page.type(args.selector, args.text, { delay: args.delayMs ?? 0 });
      return { content: [{ type: "text", text: `Typed into ${args.selector}` }] };
    }

    if (name === "press") {
      const { page } = getPageOrThrow(args.pageId);
      await page.keyboard.press(args.key);
      return { content: [{ type: "text", text: `Pressed ${args.key}` }] };
    }

    // Extract / Evaluate
    if (name === "getText") {
      const { page } = getPageOrThrow(args.pageId);
      const el = page.locator(args.selector).first();
      const txt = await el.innerText();
      return { content: [{ type: "text", text: txt }] };
    }

    if (name === "eval") {
      const { page } = getPageOrThrow(args.pageId);
      const result = await page.evaluate(new Function(`return (${args.expression});`));
      return { content: [{ type: "text", text: JSON.stringify(result) }] };
    }

    // Screenshot / Download
    if (name === "screenshot") {
      const { page } = getPageOrThrow(args.pageId);
      const buf = await page.screenshot({
        path: args.path || undefined,
        fullPage: !!args.fullPage
      });
      return {
        content: [
          { type: "text", text: `Screenshot OK${args.path ? ` -> ${args.path}` : ""}` },
          { type: "image_base64", data: buf.toString("base64"), mimeType: "image/png" }
        ]
      };
    }

    if (name === "download") {
      const { page } = getPageOrThrow(args.pageId);
      if (!args.path) throw new Error("path is required");

      if (args.mode === "click") {
        if (!args.selector) throw new Error("selector is required for mode=click");
        const [dl] = await Promise.all([
          page.waitForEvent("download"),
          page.click(args.selector)
        ]);
        await dl.saveAs(args.path);
        return { content: [{ type: "text", text: `Downloaded (click) -> ${args.path}` }] };
      } else if (args.mode === "url") {
        if (!args.url) throw new Error("url is required for mode=url");
        const resp = await page.context().request.get(args.url);
        if (!resp.ok()) throw new Error(`Download failed: ${resp.status()} ${resp.statusText()}`);
        const buf = await resp.body();
        const fs = await import("node:fs");
        await fs.promises.writeFile(args.path, buf);
        return { content: [{ type: "text", text: `Downloaded (url) -> ${args.path}` }] };
      } else {
        throw new Error("mode must be 'click' or 'url'");
      }
    }

    // Raw HTTP client
    if (name === "request") {
      const ctx = await pwRequest.newContext();
      const method = (args.method || "GET").toUpperCase();
      const res = await ctx.fetch(args.url, {
        method,
        headers: args.headers,
        data: args.data,
        timeout: args.timeoutMs ?? 30000
      });
      const status = res.status();
      const headers = Object.fromEntries((await res.headersArray()).map(h => [h.name, h.value]));
      let bodyText = await res.text();
      // Try to keep body size reasonable when returning
      if (bodyText.length > 60_000) bodyText = bodyText.slice(0, 60_000) + "...[truncated]";
      await ctx.dispose();
      return {
        content: [{ type: "text", text: JSON.stringify({ status, headers, body: bodyText }) }]
      };
    }

    return { isError: true, content: [{ type: "text", text: `Unknown tool: ${name}` }] };
  } catch (err) {
    console.error(`[MCP-Playwright ERROR] ${err?.stack || err}`);
    return { isError: true, content: [{ type: "text", text: String(err?.message || err) }] };
  }
});

process.on("SIGINT", async () => {
  console.log("[MCP-Playwright] Shutting down...");
  await resetAll().catch(() => {});
  process.exit(0);
});

const transport = new StdioServerTransport();
await server.connect(transport);
console.log("[MCP-Playwright] Server started. Awaiting requests...");
