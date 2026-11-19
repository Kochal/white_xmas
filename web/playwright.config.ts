import { defineConfig, devices } from '@playwright/test';

// The smoke test runs against the *built* site with the fixture dataset copied into
// build/data/, i.e. the same layout the Pages workflow deploys. With E2E_REAL=1 it runs
// against real pipeline output in static/data/ instead (fixture-only checks are skipped).
const real = !!process.env.E2E_REAL;
const port = Number(process.env.E2E_PORT ?? Number(process.env.PANE_PORT ?? 4172) + 1);

export default defineConfig({
	testDir: 'e2e',
	testMatch: '**/*.e2e.ts',
	timeout: 60_000,
	retries: process.env.CI ? 1 : 0,
	use: { baseURL: `http://localhost:${port}`, trace: 'retain-on-failure' },
	projects: [
		{ name: 'desktop', use: { ...devices['Desktop Chrome'] } },
		{ name: 'mobile', use: { ...devices['Pixel 7'] } }
	],
	webServer: {
		command: real
			? `npm run build && node scripts/serve-build.mjs ${port}`
			: `npm run build:fixtures && node scripts/serve-build.mjs ${port}`,
		port,
		// always build and serve fresh, so the test never runs against a stale build/
		reuseExistingServer: false,
		timeout: 180_000
	}
});
