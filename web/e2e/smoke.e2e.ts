import { expect, test } from '@playwright/test';

test('home page loads the manifest', async ({ page }) => {
	await page.goto('/');
	await expect(page.getByTestId('data-status')).toContainText('0.0-fixture');
});
