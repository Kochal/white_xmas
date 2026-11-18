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
	await expect(strip.getByRole('img')).toHaveAttribute('aria-label', /1950 to 2025/);
	await expect(strip.locator('.cell')).toHaveCount(76);

	// the selection is in the URL, so the view can be shared
	await expect(page).toHaveURL(/place=Munich/);
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
