import { describe, expect, it } from 'vitest';
import { cellCentre, cellOf, tileOf } from './grid';

describe('ERA5-Land grid (contract § Grid)', () => {
	it('maps Munich to the cell whose centre is nearest', () => {
		// lon 11.58 → i = round(191.58 / 0.1) = 1916; lat 48.14 → j = round(41.86 / 0.1) = 419
		expect(cellOf(11.58, 48.14)).toEqual({ i: 1916, j: 419 });
	});

	it('wraps longitude 180 onto i = 0 and keeps the south pole row', () => {
		expect(cellOf(180, 0)).toEqual({ i: 0, j: 900 });
		expect(cellOf(-180, -90)).toEqual({ i: 0, j: 1800 });
		expect(cellOf(179.96, 90)).toEqual({ i: 0, j: 0 });
	});

	it('normalises longitudes outside −180…180', () => {
		expect(cellOf(191.58 - 360 + 360, 48.14)).toEqual(cellOf(-168.42, 48.14));
		expect(cellOf(-348.42, 48.14)).toEqual(cellOf(11.58, 48.14));
	});

	it('returns the cell centre coordinates', () => {
		const c = cellCentre({ i: 1916, j: 419 });
		expect(c.lon).toBeCloseTo(11.6, 9);
		expect(c.lat).toBeCloseTo(48.1, 9);
	});

	it('finds the 5° point tile and the cell inside it', () => {
		// tx = floor(1916 / 50) = 38, ty = floor(419 / 50) = 8, ci = 16, cj = 19
		expect(tileOf({ i: 1916, j: 419 })).toEqual({ tx: 38, ty: 8, ci: 16, cj: 19, key: '38_8' });
		expect(tileOf({ i: 0, j: 1800 })).toEqual({ tx: 0, ty: 36, ci: 0, cj: 0, key: '0_36' });
		expect(tileOf({ i: 3599, j: 0 })).toEqual({ tx: 71, ty: 0, ci: 49, cj: 0, key: '71_0' });
	});
});
