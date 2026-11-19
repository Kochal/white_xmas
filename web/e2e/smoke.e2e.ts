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
	// the headline reads as a sentence, never "… in never"
	await expect(panel).toContainText(
		/Snow on Christmas Day: (about \d+ in 10 years|never|rarely|almost every year|every year)/
	);
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

test('Future is offered only for definitions with projections, and the tabs follow the map', async ({
	page
}) => {
	await page.goto('/?def=all_three_days');
	const layersToggle = page.getByRole('button', { name: 'Map layers' });
	if (await layersToggle.isVisible()) await layersToggle.click();
	await expect(page.getByRole('radio', { name: 'Probability' })).toBeChecked();
	await expect(page.getByRole('radio', { name: 'Future' })).toHaveCount(0);

	await page.getByLabel('Definition').selectOption('christmas_day');
	await page.getByRole('radio', { name: 'Future' }).check();
	await expect(page).toHaveURL(/layer=projection/);
	await expect(page.getByRole('radio', { name: 'Future' })).toBeChecked();

	// back to a definition without projections: the map falls back, and so do the tabs
	await page.getByLabel('Definition').selectOption('any_day');
	await expect(page).toHaveURL(/layer=probability/);
	await expect(page.getByRole('radio', { name: 'Probability' })).toBeChecked();
	await expect(page.getByRole('radio', { name: 'Future' })).toHaveCount(0);
});

test('methodology shows the threshold from the data', async ({ page }) => {
	await page.goto('/methodology/');
	const box = page.getByTestId('dataset-threshold');
	await expect(box).toContainText('Calibrated to weather stations');
	await expect(box).toContainText('Raw ERA5-Land, at least 1 cm');
	await expect(box).toContainText('Calibrated: 5 cm in ERA5-Land ≈ 1 cm at a weather station.');
});

test('a slow basemap does not leave a false "unavailable" notice', async ({ page, isMobile }) => {
	test.skip(isMobile, 'one run is enough');
	test.setTimeout(60_000);
	await page.route('https://tiles.openfreemap.org/styles/**', async (route) => {
		await new Promise((r) => setTimeout(r, 14_000));
		await route.continue();
	});
	await page.goto('/');
	const notice = page.getByRole('status').filter({ hasText: 'background map is unavailable' });
	await expect(notice).toBeVisible({ timeout: 20_000 }); // after 12 s without a basemap
	await expect(notice).toBeHidden({ timeout: 20_000 }); // gone once the style arrives
});

test('threshold switch: calibrated by default, raw ERA5-Land on demand (contract v1.5)', async ({
	page
}) => {
	await page.goto('/?at=48.1374,11.5755&place=Munich');
	const panel = page.getByTestId('place-panel');
	const both = panel.getByTestId('both-thresholds');
	await expect(both).toContainText('calibrated');
	await expect(both).toContainText('raw ERA5-Land');
	const calibrated = await panel.getByTestId('headline').innerText();
	await expect(panel.getByTestId('threshold-note')).toContainText('Calibrated: 5 cm');

	const layersToggle = page.getByRole('button', { name: 'Map layers' });
	if (await layersToggle.isVisible()) await layersToggle.click();
	await expect(page.getByRole('radio', { name: 'Calibrated to stations' })).toBeChecked();
	await expect(page.getByRole('radio', { name: 'Future' })).toHaveCount(1);

	await page.getByRole('radio', { name: 'Raw ERA5-Land (1 cm)' }).check();
	await expect(page).toHaveURL(/th=raw/);
	await expect(panel.getByTestId('headline')).not.toHaveText(calibrated);
	await expect(panel).toContainText('at least 1 cm');
	// projections are calibrated only
	await expect(page.getByRole('radio', { name: 'Future' })).toHaveCount(0);
	await expect(page.getByTestId('future-note')).toBeVisible();

	// raw maps exist for Snow on Christmas Day only: another definition falls back to calibrated
	await page.locator('#layer-controls').getByLabel('Definition').selectOption('all_three_days');
	await expect(page).toHaveURL(/th=calibrated/);
	await expect(page.getByRole('radio', { name: 'Raw ERA5-Land (1 cm)' })).toBeDisabled();
	await expect(page.getByTestId('raw-note')).toBeVisible();
});
