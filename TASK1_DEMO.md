# Task 1 demo repository and deterministic UI bug

## Selection

- **Repository:** YesFundMe (`https://github.com/Gauntlet-HQ/yes-build-me.git`)
- **Pinned revision:** `079886d51a871b2c4e43377a1a33e456d93cdd91`
- **Stack:** React 19/Vite client, Express server, SQLite; npm workspaces
- **Why this repo:** It is small, has documented seed credentials, starts with one command, and intentionally contains the exact UI bug in `packages/client/src/pages/CreateCampaign.jsx:18-20`. The catch block logs campaign-creation errors but never updates the rendered `error` state.

Pin the revision. `main` is mutable and a future teaching exercise/PR may fix the bug.

## Natural-language issue

> **Campaign creation failures are not shown to the user**
>
> After a signed-in user completes the Create a Campaign form, if `POST /api/campaigns` fails, the page should remain on the form and show the error message returned by the API. Instead, it remains on the form with no visible feedback. The error is only written to the browser console, so the user cannot tell whether submission failed or is still in progress.

The deterministic reproduction returns HTTP 503 with `{ "error": "Service temporarily unavailable" }` for only the campaign creation request. Authentication and page loading still use the real local server.

## Exact clean run

Run these commands from the root of **this bug-reproduction-agent checkout**. Node 22+ and npm 10+ are required by the selected repository.

```bash
# Clone and pin
git clone https://github.com/Gauntlet-HQ/yes-build-me.git /tmp/yes-build-me-demo
git -C /tmp/yes-build-me-demo checkout 079886d51a871b2c4e43377a1a33e456d93cdd91

# Put the handcrafted generated-test fixture where Playwright will run it
cp -R task1_fixture /tmp/yes-build-me-demo/task1-playwright
cd /tmp/yes-build-me-demo

# Install and initialize the app
npm ci
npm run seed

# Install the test runner without changing package.json/package-lock.json
npm install --no-save --package-lock=false @playwright/test@1.62.1
npx playwright install chromium
# In a clean Linux/Daytona image, use this instead if OS libraries are absent:
# npx playwright install --with-deps chromium

# Start both Vite (:5173) and Express (:3000)
npm run dev > /tmp/yesfundme-app.log 2>&1 &
APP_PID=$!

# Wait for both services
until curl -fsS http://localhost:5173/ >/dev/null && \
      curl -fsS http://localhost:3000/api/campaigns >/dev/null; do sleep 1; done

# This command is EXPECTED to exit 1 because it reproduces the product bug
set +e
npx playwright test --config=task1-playwright/playwright.config.cjs
TEST_EXIT=$?
set -e

# Cleanup after inspecting output/artifacts, while preserving the test result
kill "$APP_PID"
exit "$TEST_EXIT"
```

The standalone commands used by the agent are therefore:

- **Clone:** `git clone https://github.com/Gauntlet-HQ/yes-build-me.git <dir>` then `git checkout 079886d51a871b2c4e43377a1a33e456d93cdd91`
- **Install:** `npm ci && npm run seed && npm install --no-save --package-lock=false @playwright/test@1.62.1 && npx playwright install chromium`
- **Start:** `npm run dev` (frontend `http://localhost:5173`, backend `http://localhost:3000`)
- **Test:** `npx playwright test --config=task1-playwright/playwright.config.cjs`

## Expected failing assertion

Fixture: [`task1_fixture/reproduce.spec.js`](task1_fixture/reproduce.spec.js)

```js
await expect(
  page.getByText('Service temporarily unavailable', { exact: true }),
).toBeVisible();
```

Expected failure signature (a genuine reproduction):

```text
Error: expect(locator).toBeVisible() failed
Locator: getByText('Service temporarily unavailable', { exact: true })
Expected: visible
Error: element(s) not found
... reproduce.spec.js:35:5
```

A failure before this assertion (clone/install error, connection refusal, login failure, timeout, syntax error, or missing browser) is infrastructure/test failure and **must not** be classified as bug reproduction.

## Manual reproduction

1. Run `npm ci`, `npm run seed`, and `npm run dev` in the pinned checkout.
2. Open `http://localhost:5173/login`.
3. Sign in as `testuser` / `password123`.
4. Open `http://localhost:5173/campaigns/new`.
5. Enter:
   - Campaign Title: `Playwright campaign`
   - Description: `A sufficiently long campaign description for reproduction.`
   - Goal Amount: `100`
6. Open Chrome DevTools Console and install this one-request failure simulation (it leaves all other requests real):

   ```js
   const realFetch = window.fetch;
   window.fetch = (input, init = {}) =>
     input === '/api/campaigns' && init.method === 'POST'
       ? Promise.resolve(new Response(
           JSON.stringify({ error: 'Service temporarily unavailable' }),
           { status: 503, headers: { 'Content-Type': 'application/json' } },
         ))
       : realFetch(input, init);
   ```

7. Click **Create Campaign**.
8. Observe that the button returns from **Saving...** to **Create Campaign**, but no error appears anywhere in the page. DevTools Console contains the error.
9. Expected behavior: a visible error explains that campaign creation failed (for the deterministic response, `Service temporarily unavailable`).

For a less tool-heavy manual simulation, stop the Express server after login while leaving Vite running, then submit valid form data. The proxy/fetch error is logged but no user-facing failure appears.

## Validation evidence

Validated locally on **2026-08-29** with Node `v24.9.0`, npm `11.6.1`, Chromium, and Playwright `1.62.1`:

- `npm ci`: succeeded (421 packages)
- `npm run seed`: succeeded (5 users, 10 campaigns, 28 donations)
- Readiness checks: frontend and backend both returned HTTP 200
- Reproduction test: reached line 35 and failed with `element(s) not found`, exit code 1
- Control check: changing the temporary clone's catch block to `setError(err.message)` made the exact same test pass (`1 passed` in 896 ms). This confirms the assertion tests the intended defect rather than an impossible locator.
- Playwright is configured to retain a screenshot and trace on failure. In the target checkout these are written under `test-results/`.

No selected-repository source was copied or edited in this project; only a Playwright fixture and documentation were added.

## Risks and mitigations

| Risk | Impact / mitigation |
|---|---|
| Upstream bug gets fixed | Always checkout the pinned commit above. A local fallback clone/archive should preserve that commit. |
| Node/native SQLite mismatch | Repo declares Node >=22. Use a Node 22 image; `better-sqlite3` may need build tools if no prebuilt binary exists. |
| Missing Linux browser libraries | Use `npx playwright install --with-deps chromium` in Daytona (with sufficient privileges). |
| Services are not ready | Poll both URLs before testing. Do not classify connection errors as reproduction. |
| Port/binding differences | Browser execution inside the sandbox can use `localhost`. If Daytona must expose Vite externally, start the client with `--host 0.0.0.0`. |
| Seed credentials unavailable | Run `npm run seed` before every clean demo; it recreates the SQLite database deterministically. |
| Interception seems artificial | It controls only the error condition. Login, routing, form validation, submit handler, API client error handling, and rendering are real app code. The source itself labels this behavior as an intentional bug. |
| `npm audit` reports vulnerabilities | The validated install reported 19 dependency findings. Use only an isolated disposable sandbox and do not expose it publicly. |
| Exit code 1 is ambiguous | Require the assertion signature and source location above; setup, browser, login, and navigation failures are not reproductions. |
| npm install mutates the checkout | `--no-save --package-lock=false` avoids manifest/lock changes; destroy the sandbox after execution. |
