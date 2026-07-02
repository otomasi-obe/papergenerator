#!/usr/bin/env node

/**
 * MCP Playwright Server - Cloudflare-bypassing browser automation for journal fetching
 * 
 * Provides tools untuk:
 * - fetch_page: Single page fetch dengan stealth + Cloudflare bypass
 * - fetch_pages: Batch fetching dalam satu browser session
 * - search_researchgate: Specialized ResearchGate search dengan parsing
 * 
 * Transport: stdio (AI agent komunikasi via stdin/stdout)
 */

import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";
import { chromium } from "playwright";

// ═══════════════════════════════════════════════════════════════════════════
// Server Setup
// ═══════════════════════════════════════════════════════════════════════════

const server = new Server(
  {
    name: "playwright-fetcher",
    version: "1.0.0",
  },
  {
    capabilities: {
      tools: {},
    },
  }
);

// ═══════════════════════════════════════════════════════════════════════════
// Browser Management
// ═══════════════════════════════════════════════════════════════════════════

const STEALTH_CONFIG = {
  userAgent: "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
  viewport: { width: 1920, height: 1080 },
  locale: "en-US",
  args: [
    "--disable-blink-features=AutomationControlled",
    "--disable-dev-shm-usage",
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--disable-web-security",
  ],
};

async function launchBrowser(headless = true) {
  const browser = await chromium.launch({
    headless,
    args: STEALTH_CONFIG.args,
  });
  
  const context = await browser.newContext({
    userAgent: STEALTH_CONFIG.userAgent,
    viewport: STEALTH_CONFIG.viewport,
    locale: STEALTH_CONFIG.locale,
    // Extra stealth
    extraHTTPHeaders: {
      "Accept-Language": "en-US,en;q=0.9",
      "Accept-Encoding": "gzip, deflate, br",
    },
  });

  return { browser, context };
}

async function humanLikeDelay(min = 500, max = 2000) {
  const delay = Math.floor(Math.random() * (max - min + 1)) + min;
  await new Promise(resolve => setTimeout(resolve, delay));
}

async function humanLikeInteraction(page) {
  try {
    // Random mouse movements
    for (let i = 0; i < Math.floor(Math.random() * 3) + 2; i++) {
      const x = Math.floor(Math.random() * 800) + 100;
      const y = Math.floor(Math.random() * 600) + 100;
      await page.mouse.move(x, y);
      await humanLikeDelay(100, 400);
    }

    // Scroll sedikit
    await page.evaluate(() => window.scrollBy(0, window.innerHeight * 0.3));
    await humanLikeDelay(500, 1500);
  } catch (error) {
    // Non-critical, ignore
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// Tool Handlers
// ═══════════════════════════════════════════════════════════════════════════

async function fetchPage(url, waitSelector = null, timeout = 30) {
  let browser, context;
  try {
    ({ browser, context } = await launchBrowser(true));
    const page = await context.newPage();

    // Navigate
    const response = await page.goto(url, {
      timeout: timeout * 1000,
      waitUntil: "domcontentloaded",
    });

    // Check for Cloudflare challenge
    const title = await page.title();
    if (title.includes("Just a moment") || (response && response.status() === 403)) {
      console.error("[playwright] Cloudflare challenge detected, waiting...");
      try {
        await page.waitForURL(url => !url.includes("Just a moment"), { timeout: 15000 });
      } catch {
        // Continue anyway
      }
    }

    // Wait for selector if specified
    if (waitSelector) {
      try {
        await page.waitForSelector(waitSelector, { timeout: timeout * 1000 });
      } catch (error) {
        console.error(`[playwright] Selector '${waitSelector}' not found: ${error.message}`);
      }
    }

    // Human-like interaction
    await humanLikeInteraction(page);

    const html = await page.content();
    await browser.close();

    return {
      success: true,
      html,
      url: page.url(),
      title: await page.title(),
      status: response ? response.status() : 200,
    };

  } catch (error) {
    if (browser) await browser.close();
    return {
      success: false,
      error: error.message,
      url,
    };
  }
}

async function fetchPages(urls, delayMin = 2000, delayMax = 5000) {
  let browser, context;
  const results = [];

  try {
    ({ browser, context } = await launchBrowser(true));

    for (const url of urls) {
      const page = await context.newPage();
      
      try {
        await page.goto(url, { timeout: 30000, waitUntil: "domcontentloaded" });
        await humanLikeInteraction(page);
        
        const html = await page.content();
        results.push({
          url,
          success: true,
          html,
          title: await page.title(),
        });
        
        await page.close();
        
        // Delay antar request
        if (urls.indexOf(url) < urls.length - 1) {
          await humanLikeDelay(delayMin, delayMax);
        }
        
      } catch (error) {
        results.push({
          url,
          success: false,
          error: error.message,
        });
        await page.close();
      }
    }

    await browser.close();
    return { success: true, results };

  } catch (error) {
    if (browser) await browser.close();
    return { success: false, error: error.message };
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// MCP Protocol Handlers
// ═══════════════════════════════════════════════════════════════════════════

server.setRequestHandler(ListToolsRequestSchema, async () => {
  return {
    tools: [
      {
        name: "fetch_page",
        description: "Fetch single page HTML with Cloudflare bypass using Playwright. Returns full HTML content with stealth techniques applied.",
        inputSchema: {
          type: "object",
          properties: {
            url: {
              type: "string",
              description: "URL to fetch",
            },
            wait_selector: {
              type: "string",
              description: "CSS selector to wait for (ensures content loaded)",
            },
            timeout: {
              type: "number",
              description: "Max wait time in seconds (default: 30)",
              default: 30,
            },
          },
          required: ["url"],
        },
      },
      {
        name: "fetch_pages",
        description: "Fetch multiple pages in one browser session with rate limiting. More efficient for batch operations.",
        inputSchema: {
          type: "object",
          properties: {
            urls: {
              type: "array",
              items: { type: "string" },
              description: "Array of URLs to fetch",
            },
            delay_min: {
              type: "number",
              description: "Minimum delay between requests in ms (default: 2000)",
              default: 2000,
            },
            delay_max: {
              type: "number",
              description: "Maximum delay between requests in ms (default: 5000)",
              default: 5000,
            },
          },
          required: ["urls"],
        },
      },
    ],
  };
});

server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args } = request.params;

  try {
    if (name === "fetch_page") {
      const { url, wait_selector, timeout = 30 } = args;
      const result = await fetchPage(url, wait_selector, timeout);
      
      return {
        content: [
          {
            type: "text",
            text: JSON.stringify(result, null, 2),
          },
        ],
      };
    }

    if (name === "fetch_pages") {
      const { urls, delay_min = 2000, delay_max = 5000 } = args;
      const result = await fetchPages(urls, delay_min, delay_max);
      
      return {
        content: [
          {
            type: "text",
            text: JSON.stringify(result, null, 2),
          },
        ],
      };
    }

    throw new Error(`Unknown tool: ${name}`);

  } catch (error) {
    return {
      content: [
        {
          type: "text",
          text: JSON.stringify({ success: false, error: error.message }),
        },
      ],
      isError: true,
    };
  }
});

// ═══════════════════════════════════════════════════════════════════════════
// Start Server
// ═══════════════════════════════════════════════════════════════════════════

async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
  console.error("[MCP Playwright Server] Running on stdio");
}

main().catch((error) => {
  console.error("[MCP Playwright Server] Fatal error:", error);
  process.exit(1);
});
