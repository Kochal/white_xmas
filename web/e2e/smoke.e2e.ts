import { expect, test } from '@playwright/test';

test('map loads, search "Munich" opens the panel with a year strip', async ({ page }) => {
	await page.goto('/');
	await expect(page.getByText('Fixture data')).toBeVisible();
	await expect(page.locator('.maplibregl-canvas')).toBeVisible({ timeout: 20_000 });

	const search = page.getByRole('combobox', { name: 'Search for a place' });
	await search.fill('Munich');
	await expect(page.getByRole('option').first()).toContainText('Munich');
	await search.press('Enter');

	const panel = page.getByTestId('place-panel');
	await expect(panel.getByRole('heading', { name: 'Munich' })).toBeVisible();
	await expect(panel.getByTestId('headline')).toHaveText(/\d+%/);
	const strip = panel.getByTestId('year-strip');
	await expect(strip.getByRole('group')).toHaveAttribute('aria-label', /1950 to 2025/);
	await expect(strip.locator('.cell')).toHaveCount(76);
	// a year's details are reachable by tap and keyboard
	await strip.getByRole('button', { name: /^1987:/ }).click();
	await expect(strip.getByTestId('year-detail')).toContainText('1987:');
	await page.keyboard.press('ArrowRight');
	await expect(strip.getByTestId('year-detail')).toContainText('1988:');
	await expect(strip.getByRole('table')).toHaveCount(1);

	// the selection is in the URL, so the view can be shared
	await expect(page).toHaveURL(/place=Munich/);

	// Escape closes the panel (outside the search box)
	await panel.getByTestId('headline').click();
	await page.keyboard.press('Escape');
	await expect(panel).toBeHidden();
});

test('phone: the expanded sheet can be collapsed and closed', async ({ page, isMobile }) => {
	test.skip(!isMobile, 'bottom sheet is phone-only');
	await page.goto('/?at=48.1374,11.5755&place=Munich');
	const panel = page.getByTestId('place-panel');
	await expect(panel.getByTestId('headline')).toBeVisible();

	await panel.getByRole('button', { name: 'Expand details' }).click();
	// the search card must not cover the sheet's heading or controls
	await expect(page.getByRole('combobox', { name: 'Search for a place' })).toBeHidden();
	await expect(panel.getByRole('heading', { name: 'Munich' })).toBeVisible();
	await panel.getByRole('button', { name: 'Collapse details' }).click();
	await panel.getByRole('button', { name: 'Expand details' }).click();
	await panel.getByRole('button', { name: 'Close details' }).click(); // fails if covered
	await expect(panel).toBeHidden();
	await expect(page.getByRole('combobox', { name: 'Search for a place' })).toBeVisible();
});

test('a shared URL restores the selected place', async ({ page }) => {
	await page.goto('/?layer=change&at=48.1374,11.5755&place=Munich');
	await expect(
		page.getByTestId('place-panel').getByRole('heading', { name: 'Munich' })
	).toBeVisible();
	const layersToggle = page.getByRole('button', { name: 'Map layers' });
	if (await layersToggle.isVisible()) await layersToggle.click(); // phones fold the controls
	await expect(page.getByRole('radio', { name: 'Change' })).toBeChecked();
});

test('a shared URL with a name that does not match the place shows coordinates', async ({
	page
}) => {
	await page.goto('/?at=47.0000,15.0000&place=Munich');
	const heading = page.getByTestId('place-panel').getByRole('heading', { level: 2 });
	await expect(heading).toHaveText('47.0°N 15.0°E');
});

test('no horizontal scroll at 360 px', async ({ page }) => {
	await page.setViewportSize({ width: 360, height: 740 });
	for (const path of ['/', '/rankings/', '/methodology/', '/downloads/', '/about/']) {
		await page.goto(path);
		const [scroll, inner] = await page.evaluate(() => [
			document.documentElement.scrollWidth,
			window.innerWidth
		]);
		expect(scroll, path).toBeLessThanOrEqual(inner);
	}
});

test('text typed before the app hydrates still searches', async ({ page }) => {
	// hold back the app entry so the prerendered search box is usable before hydration
	let release!: () => void;
	const gate = new Promise<void>((r) => (release = r));
	await page.route('**/_app/immutable/entry/app.*.js', async (route) => {
		await gate;
		await route.continue();
	});
	await page.goto('/', { waitUntil: 'commit' });
	const search = page.getByRole('combobox', { name: 'Search for a place' });
	await search.fill('Munich');
	release();
	const list = page.getByRole('listbox', { name: 'Places' });
	await expect(list.getByRole('option').first()).toContainText('Munich', { timeout: 15_000 });
});

test('Future: change vs today keeps the warming level and explains the hatching', async ({
	page
}) => {
	await page.goto('/?layer=projection&period=3');
	const layersToggle = page.getByRole('button', { name: 'Map layers' });
	if (await layersToggle.isVisible()) await layersToggle.click();
	await expect(page.getByRole('radio', { name: 'Future' })).toBeChecked();
	// the select shows the short label; the derived "approx" text sits beside it (contract v1.3)
	await expect(page.getByLabel('Warming')).toHaveValue('3');
	await expect(page.getByTestId('level-note')).toContainText('not reached under SSP2-4.5');

	await page.getByRole('radio', { name: 'Change vs today' }).check();
	await expect(page).toHaveURL(/layer=projection_change/);
	await expect(page.getByLabel('Warming')).toHaveValue('3');
	const legend = page.getByRole('region', { name: 'Legend' });
	await expect(legend.getByRole('heading', { name: 'Change vs today' })).toBeVisible();
	const key = legend.getByRole('button', { name: 'Key' });
	if (await key.isVisible()) await key.click();
	await expect(legend).toContainText('fewer than 2 in 3 models agree on the direction of change');
	await expect(legend.getByTestId('legend-ends')).toContainText('fewer');
	await expect(legend).not.toContainText(/\b(brown|blue|red)\b/i);
});
