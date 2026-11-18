import { defineConfig, devices } from '@playwright/test';

// The smoke test runs against the *built* site with the fixture dataset copied into
// build/data/, i.e. the same layout the Pages workflow deploys.
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
		command: `npm run build:fixtures && node scripts/serve-build.mjs ${port}`,
		port,
		reuseExistingServer: !process.env.CI,
		timeout: 180_000
	}
});
