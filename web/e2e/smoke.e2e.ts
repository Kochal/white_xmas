import { expect, test } from '@playwright/test';

/** E2E_REAL=1: running against real pipeline output (static/data), not the fixtures. */
const REAL = !!process.env.E2E_REAL;

test('map loads, search "Munich" opens the panel with a year strip', async ({ page }) => {
	await page.goto('/');
	if (!REAL) await expect(page.getByText('Fixture data')).toBeVisible();
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
		// a wide font, so a run on Windows/macOS is as strict as CI's Linux fonts
		await page.addStyleTag({
			content: '* { font-family: Verdana, "DejaVu Sans", sans-serif !important; }'
		});
		await page.waitForTimeout(300);
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
	// approx is derived by the pipeline (fixtures use a "not reached" example)
	await expect(page.getByTestId('level-note')).toContainText(
		REAL ? /\+3 °C\s+global\s+warming:\s+\S+/ : 'not reached under SSP2-4.5'
	);

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
	if (REAL) {
		// the real export has raw maps for every definition: raw stays selected
		await expect(page).toHaveURL(/th=raw/);
		await expect(page.getByTestId('raw-note')).toHaveCount(0);
	} else {
		// fixtures have raw maps for Snow on Christmas Day only: falls back to calibrated
		await expect(page).toHaveURL(/th=calibrated/);
		await expect(page.getByRole('radio', { name: 'Raw ERA5-Land (1 cm)' })).toBeDisabled();
		await expect(page.getByTestId('raw-note')).toBeVisible();
	}
});

// --- states and provinces (contract v1.6): fixtures carry the pipeline's admin1 sample
// (Austria, Germany, Finland, Italy, Liechtenstein, Cyprus buffer zone; fake values)

/** Opens the layer controls on phones, where they are folded behind a button. */
async function openControls(page: import('@playwright/test').Page) {
	const toggle = page.getByRole('button', { name: 'Map layers' });
	if ((await toggle.isVisible()) && (await toggle.getAttribute('aria-expanded')) !== 'true')
		await toggle.click();
}

async function closeControls(page: import('@playwright/test').Page) {
	const toggle = page.getByRole('button', { name: 'Map layers' });
	if ((await toggle.isVisible()) && (await toggle.getAttribute('aria-expanded')) === 'true')
		await toggle.click();
}

test('states and provinces load only when asked', async ({ page }) => {
	const adminRequests: string[] = [];
	page.on('request', (r) => {
		if (r.url().includes('/admin1/')) adminRequests.push(new URL(r.url()).pathname);
	});
	await page.goto('/');
	await expect(page.locator('.maplibregl-canvas')).toBeVisible({ timeout: 20_000 });
	await openControls(page);
	await expect(page.getByTestId('regions-toggle')).not.toBeChecked();
	await page.waitForTimeout(500);
	expect(adminRequests).toEqual([]);

	await page.getByTestId('regions-toggle').check();
	await expect(page.getByTestId('regions-hint')).toContainText('Click a state or province');
	// the index and the outlines, but no country file until a region opens
	expect(adminRequests.some((u) => u.endsWith('/admin1/index.json'))).toBe(true);
	expect(adminRequests.some((u) => u.endsWith('/admin1/boundaries.json'))).toBe(true);
	expect(adminRequests.some((u) => /\/admin1\/c\//.test(u))).toBe(false);
	await expect(page).toHaveURL(/regions=1/);
});

test('click a state: the region panel shows the numbers and a deep link', async ({ page }) => {
	await page.goto('/?map=6/48.9/11.3');
	await expect(page.locator('.maplibregl-canvas')).toBeVisible({ timeout: 20_000 });
	await openControls(page);
	await page.getByTestId('regions-toggle').check();
	await expect(page.getByTestId('regions-hint')).toContainText('Click a state or province');
	await closeControls(page);

	const canvas = page.locator('.maplibregl-canvas');
	const box = (await canvas.boundingBox())!;
	const panel = page.getByTestId('region-panel');
	// the click only hits the region once its outlines are drawn
	await expect(async () => {
		await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
		await expect(panel).toBeVisible({ timeout: 1500 });
	}).toPass({ timeout: 20_000 });

	await expect(panel.getByRole('heading', { level: 2 })).toHaveText(/\S/);
	await expect(panel.getByTestId('headline')).toHaveText(/\d+%/);
	await expect(panel.getByTestId('pop-weighted')).toContainText(
		/places where people live|No town or city/
	);
	// the headline says what the number is (S8), and the borders switch is the user's, not forced
	await expect(panel).toContainText(/of the land in .+ has snow/);
	await expect(panel.getByTestId('region-series').getByRole('img')).toHaveAttribute(
		'aria-label',
		/1950 to 2025/
	);
	await expect(panel.getByTestId('trend-significance')).toContainText(
		/likely trend|no clear trend/
	);
	// the main line carries no p-value; the note explains the adjusted test
	await expect(panel.getByTestId('region-trend')).not.toContainText(/p [=<]/);
	await expect(panel.getByTestId('trend-note')).toContainText('Benjamini');
	await expect(panel.getByTestId('region-trend')).toContainText('percentage points per decade');
	await expect(panel.getByTestId('region-spread')).toContainText('Inside the region');
	await expect(panel.getByRole('heading', { name: 'By decade' })).toBeVisible();
	await expect(panel.getByRole('heading', { name: 'In a warmer world' })).toBeVisible();
	await expect(panel.getByTestId('method-link')).toHaveAttribute('href', /methodology/);
	await expect(page).toHaveURL(/#\/region\/[A-Z0-9-]+$/);
	// a region and a point are never open together
	await expect(page.getByTestId('place-panel')).toHaveCount(0);

	// Escape closes the panel and drops the link's hash
	await panel.getByTestId('headline').click();
	await page.keyboard.press('Escape');
	await expect(panel).toBeHidden();
	await expect(page).not.toHaveURL(/#\/region\//);
});

test('#/region/<id> opens the region, also after a reload, and a bad id says so', async ({
	page
}) => {
	await page.goto('/#/region/AT-7');
	const panel = page.getByTestId('region-panel');
	await expect(panel.getByRole('heading', { level: 2 })).toHaveText('Tyrol');
	await expect(panel.getByTestId('headline')).toHaveText(/\d+%/);
	await expect(panel).toContainText('Austria');
	await page.reload();
	await expect(page.getByTestId('region-panel').getByRole('heading', { level: 2 })).toHaveText(
		'Tyrol'
	);

	// a region without values (Cyprus buffer zone: no land cells) says why
	await page.goto('/#/region/CNM');
	await expect(page.getByTestId('region-panel')).toContainText(/no values/i);
	await expect(page.getByTestId('region-flag-no_land')).toBeVisible();

	await page.goto('/#/region/XX-NOPE');
	await expect(page.getByTestId('region-panel')).toHaveCount(0);
	// shown outside the layer controls, so a phone user sees it too
	await expect(page.getByTestId('regions-note')).toBeVisible();
	await expect(page.getByTestId('regions-note')).toContainText('no state or province');
});

test('a small region carries the low resolution note', async ({ page }) => {
	// Liechtenstein's municipalities are first-level units in the sample: all low_res
	await page.goto('/rankings/');
	await page.getByTestId('region-country').selectOption('LIE');
	const link = page.getByTestId('region-ranking').locator('tbody tr').first().getByRole('link');
	await expect(link).toBeVisible({ timeout: 20_000 });
	await expect(page.getByTestId('region-ranking')).toContainText('low resolution');
	await link.click();
	const panel = page.getByTestId('region-panel');
	await expect(panel.getByRole('heading', { level: 2 })).toBeVisible();
	await expect(panel.getByTestId('region-flag-low_res')).toContainText('Low resolution');
});

test('region panel follows the threshold switch and the definition', async ({ page }) => {
	await page.goto('/#/region/DE-BY');
	const panel = page.getByTestId('region-panel');
	const both = panel.getByTestId('both-thresholds');
	await expect(both).toContainText('calibrated');
	await expect(both).toContainText('raw ERA5-Land');
	const calibrated = await panel.getByTestId('headline').innerText();
	await expect(panel.getByTestId('threshold-note')).toContainText('Calibrated: 5 cm');

	await openControls(page);
	await page.getByRole('radio', { name: 'Raw ERA5-Land (1 cm)' }).check();
	await expect(panel.getByTestId('headline')).not.toHaveText(calibrated);
	await expect(panel).toContainText('at least 1 cm');
	await closeControls(page);

	await panel.getByLabel('Definition').selectOption('any_day');
	await expect(panel).toContainText('Snow on any of the three days');
});

test('search finds states and provinces next to places', async ({ page }) => {
	await page.goto('/');
	await expect(page.locator('.maplibregl-canvas')).toBeVisible({ timeout: 20_000 });
	const search = page.getByRole('combobox', { name: 'Search for a place' });
	await search.fill('Bavaria');
	const option = page
		.getByRole('option')
		.filter({ has: page.getByTestId('region-type') })
		.first();
	await expect(option).toContainText('Bavaria');
	await expect(option).toContainText('Germany');
	await option.click();
	const panel = page.getByTestId('region-panel');
	await expect(panel.getByRole('heading', { level: 2 })).toHaveText('Bavaria');
	await expect(page).toHaveURL(/#\/region\/DE-BY/);

	// a city still opens the place panel, and replaces the region
	await search.fill('Munich');
	await expect(page.getByRole('option').first()).toContainText('Munich');
	await search.press('Enter');
	await expect(page.getByTestId('place-panel')).toBeVisible();
	await expect(panel).toHaveCount(0);
	await expect(page).not.toHaveURL(/#\/region\//);
});

test('rankings: regions in a country, the world list, and the region search', async ({ page }) => {
	await page.goto('/rankings/');
	const table = page.getByTestId('region-ranking');
	await expect(table).toBeVisible({ timeout: 20_000 });
	// world, snowiest: low-resolution regions (Liechtenstein) are left out
	await expect(table.locator('tbody tr').first()).toContainText(/\d+%/);
	await expect(table).not.toContainText('low resolution');

	await page.getByTestId('region-country').selectOption('DEU');
	await expect(page.getByRole('heading', { name: /regions in Germany/ })).toBeVisible();
	await expect(table.locator('tbody tr')).toHaveCount(16);
	await expect(table.locator('tbody tr').first().getByRole('link')).toHaveAttribute(
		'href',
		/regions=1#\/region\/DE-/
	);

	await page.getByRole('radio', { name: 'Biggest decline' }).check();
	await expect(table.getByRole('columnheader', { name: 'Change' })).toBeVisible();
	await page.getByRole('radio', { name: 'Least snowy' }).check();
	await expect(page.getByRole('heading', { name: /Least snowy regions in Germany/ })).toBeVisible();

	// the search box ignores the country and ranking, and the link opens the map on the region
	await page.getByTestId('region-find').fill('tyrol');
	// "Tyrol" first, then the Italian "Trentino-South Tyrol"
	await expect(table.locator('tbody tr')).toHaveCount(2);
	await expect(table.locator('tbody tr').first()).toContainText('Tyrol');
	await table.getByRole('link', { name: 'Tyrol', exact: true }).click();
	await expect(page.getByTestId('region-panel').getByRole('heading', { level: 2 })).toHaveText(
		'Tyrol'
	);
	await expect(page).toHaveURL(/#\/region\/AT-7/);
});

test('region panel stays within 360 px', async ({ page }) => {
	await page.setViewportSize({ width: 360, height: 740 });
	await page.goto('/#/region/DE-BY');
	const panel = page.getByTestId('region-panel');
	await expect(panel.getByTestId('headline')).toBeVisible();
	const grip = panel.getByRole('button', { name: 'Expand details' });
	if (await grip.isVisible()) await grip.click();
	await page.addStyleTag({
		content: '* { font-family: Verdana, "DejaVu Sans", sans-serif !important; }'
	});
	await page.waitForTimeout(300);
	const [scroll, inner] = await page.evaluate(() => [
		document.documentElement.scrollWidth,
		window.innerWidth
	]);
	expect(scroll).toBeLessThanOrEqual(inner);
	// the scrolling body, not the clipped panel: nothing in it may be wider than the panel
	const [pw, cw] = await panel
		.locator('#panel-body')
		.evaluate((el) => [el.scrollWidth, el.clientWidth]);
	expect(pw).toBeLessThanOrEqual(cw);
});

test('a region link with a long id (M1) or an id the parser rejects says there is no such region', async ({
	page
}) => {
	// 25 characters, a valid pattern, not in the data
	await page.goto('/#/region/SVN-JUGOVZHODNA-SLOVENIJA');
	await expect(page.getByTestId('regions-note')).toContainText('no state or province');
	await expect(page.getByTestId('region-panel')).toHaveCount(0);

	// longer than any id: the parser refuses it, and the page must still say so
	await page.goto('/#/region/' + 'A'.repeat(60));
	await expect(page.getByTestId('regions-note')).toContainText('no state or province');
	// the note can be dismissed
	await page.getByRole('button', { name: 'Dismiss this message' }).click();
	await expect(page.getByTestId('regions-note')).toHaveCount(0);
});

test('opening a region does not switch the borders layer on', async ({ page }) => {
	await page.goto('/#/region/DE-BY');
	await expect(page.getByTestId('region-panel').getByTestId('headline')).toBeVisible();
	await expect(page).not.toHaveURL(/regions=1/);
	await openControls(page);
	await expect(page.getByTestId('regions-toggle')).not.toBeChecked();
});

test('when the region data cannot be loaded the page says so, also on phones', async ({ page }) => {
	await page.route('**/admin1/**', (route) => route.abort());
	// a deep link: the index fails, so no panel, but a visible message and no page error
	const errors: string[] = [];
	page.on('pageerror', (e) => errors.push(e.message));
	await page.goto('/#/region/DE-BY');
	const note = page.getByTestId('regions-note');
	await expect(note).toBeVisible({ timeout: 15_000 });
	await expect(note).toContainText('could not be loaded');
	await expect(page.getByTestId('region-panel')).toHaveCount(0);
	// the rest of the site keeps working
	const search = page.getByRole('combobox', { name: 'Search for a place' });
	await search.fill('Munich');
	await expect(page.getByRole('option').first()).toContainText('Munich');
	expect(errors).toEqual([]);
});

test('a bad region id with the region data blocked still shows a message', async ({ page }) => {
	await page.route('**/admin1/**', (route) => route.abort());
	await page.goto('/#/region/XX-NOPE');
	await expect(page.getByTestId('regions-note')).toBeVisible({ timeout: 15_000 });
});

test('switching the borders on with the outlines blocked reports it and switches back off', async ({
	page
}) => {
	await page.route('**/admin1/boundaries.json', (route) => route.abort());
	await page.goto('/');
	await expect(page.locator('.maplibregl-canvas')).toBeVisible({ timeout: 20_000 });
	await openControls(page);
	await page.getByTestId('regions-toggle').check();
	await closeControls(page);
	await expect(page.getByTestId('regions-note')).toContainText('borders could not be loaded', {
		timeout: 20_000
	});
	await openControls(page);
	await expect(page.getByTestId('regions-toggle')).not.toBeChecked();
});

test('rankings: ties are explained, the type is shown, Antarctica is not ranked', async ({
	page
}) => {
	await page.goto('/rankings/');
	const table = page.getByTestId('region-ranking');
	await expect(table).toBeVisible({ timeout: 20_000 });
	await expect(page.getByTestId('rank-summary')).toContainText('Ties are ordered by');
	await page.getByTestId('region-country').selectOption('DEU');
	// the type next to the country-less list: "State"
	await expect(table.locator('tbody tr').first()).toContainText('State');
	await page.getByTestId('region-country').selectOption('');
	await page.getByRole('radio', { name: 'Biggest decline' }).check();
	await expect(page.getByTestId('rank-summary')).toHaveCount(0);
});

test('search shows the type of a region next to its name', async ({ page }) => {
	await page.goto('/');
	await expect(page.locator('.maplibregl-canvas')).toBeVisible({ timeout: 20_000 });
	await page.getByRole('combobox', { name: 'Search for a place' }).fill('Bavaria');
	await expect(page.getByTestId('region-type').first()).toHaveText('State');
});
