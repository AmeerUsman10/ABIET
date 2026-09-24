// End-to-end UI test: drives the real web UI in Chromium against a running ABIET
// server whose AI provider is tests/e2e/mock_openai.py. See tests/README.md.
//
//   node tests/e2e/ui.test.cjs [base-url] [screenshot-dir]

const assert = require("node:assert/strict");
const { chromium } = require("playwright");

const BASE = process.argv[2] || "http://127.0.0.1:8000";
const SHOTS = process.argv[3] || "";

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1360, height: 900 } });
  const problems = [];
  page.on("console", (m) => { if (m.type() === "error") problems.push(`console: ${m.text()}`); });
  page.on("pageerror", (e) => problems.push(`pageerror: ${e.message}`));
  const idle = () => page.waitForFunction(() => !document.querySelector(".thread .thinking"), null, { timeout: 20000 });
  const lastAnswer = () => page.locator(".answer").last();
  const ask = async (question) => {
    await page.fill(".composer textarea", question);
    await page.keyboard.press("Enter");
    await idle();
  };
  const step = async (name, fn) => {
    try {
      await fn();
      console.log(`ok - ${name}`);
    } catch (err) {
      if (SHOTS) await page.screenshot({ path: `${SHOTS}/failed.png`, fullPage: true });
      throw new Error(`${name}: ${err.message}`);
    }
  };

  try {
    await step("register the first account", async () => {
      await page.goto(BASE);
      await page.click("text=Create account");
      await page.fill("input[name=username]", "e2e");
      await page.fill("input[name=email]", "e2e@example.com");
      await page.fill("input[name=password]", "e2e-password-123");
      await page.click("button[type=submit]");
      await page.waitForSelector("text=Connect a database to get started");
    });

    await step("add the demo database", async () => {
      await page.click("text=Try the demo database");
      await page.waitForSelector(".example-btn");
      await page.waitForSelector(".schema-table");
      assert.equal(await page.locator(".schema-table").count(), 8);
    });

    await step("ask a question and get a chart", async () => {
      await page.click("text=What was our monthly revenue over the last 12 months?");
      await page.keyboard.press("Enter");
      await idle();
      await page.waitForSelector(".answer .viz svg path.line");
      assert.match(await lastAnswer().innerText(), /Success/);
      assert.match(await lastAnswer().locator(".sql-block pre").innerText(), /strftime/);
    });

    await step("ask a follow-up question", async () => {
      await page.waitForSelector(".chip >> text=Follow-up to:");
      await ask("Only 2025 please");
      assert.match(await lastAnswer().innerText(), /2025/);
    });

    await step("start a new conversation with a grouped bar chart", async () => {
      await page.click("text=New conversation");
      await ask("Revenue by region and customer segment");
      await page.waitForSelector(".answer .legend");
      assert.equal(await lastAnswer().locator(".legend .key").count(), 4);
    });

    await step("auto-repair a failing query", async () => {
      await ask("show customers per region (broken)");
      assert.match(await lastAnswer().innerText(), /Auto-repaired/);
    });

    await step("block writes on a read-only connection", async () => {
      await ask("delete all cancelled orders");
      const text = await lastAnswer().innerText();
      assert.match(text, /Blocked/);
      assert.match(text, /read-only/);
    });

    await step("ask a clarifying question", async () => {
      await ask("how are we doing");
      assert.match(await lastAnswer().innerText(), /Needs clarification/);
    });

    await step("approve an answer so ABIET learns it", async () => {
      await page.locator(".answer").first().locator('button[aria-label="Mark answer correct"]').click();
      await page.waitForSelector("text=Thanks! ABIET will reuse");
    });

    await step("run SQL directly and view it as a table", async () => {
      await page.click('.seg button:has-text("SQL")');
      await page.fill(".composer textarea", "SELECT status, COUNT(*) AS orders FROM orders GROUP BY status");
      await page.keyboard.press("Control+Enter");
      await idle();
      assert.equal(await lastAnswer().locator("table.data tbody tr").count(), 5);
    });

    await step("history lists every query", async () => {
      await page.click("nav >> text=History");
      await page.waitForSelector(".list-item");
      assert.ok((await page.locator(".list-item").count()) >= 7);
    });

    await step("connections show what was learned", async () => {
      await page.click("nav >> text=Connections");
      await page.waitForSelector(".conn-card");
      await page.click('.conn-card button:has-text("Learned")');
      await page.waitForSelector(".examples-list >> text=approved");
    });

    await step("insights summarize usage", async () => {
      await page.click("nav >> text=Insights");
      await page.waitForSelector(".kpi");
      const queries = await page.locator(".kpi .value").first().innerText();
      assert.ok(Number(queries) >= 7, `expected at least 7 queries, got ${queries}`);
      await page.waitForSelector(".viz svg");
    });

    await step("mobile layout has no horizontal scrolling", async () => {
      await page.click("nav >> text=Ask");
      await page.setViewportSize({ width: 390, height: 844 });
      await page.waitForTimeout(300);
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth), false);
    });

    await step("the session survives a reload", async () => {
      await page.reload();
      await page.waitForSelector(".topbar");
    });

    await step("no browser errors", async () => {
      assert.deepEqual(problems, []);
    });
  } finally {
    await browser.close();
  }
})().catch((err) => {
  console.error(`not ok - ${err.message}`);
  process.exit(1);
});
