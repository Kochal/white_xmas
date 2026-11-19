import { describe, expect, it } from 'vitest';
import {
	decadeProbabilities,
	isWhite,
	olsTrend,
	probability,
	yearStrip,
	type YearState
} from './derive';
import { cellHistory, decodePointTile } from './points';

const N = null;

describe('isWhite: the three definitions, unknown when a needed day is missing (as the pipeline)', () => {
	it('christmas_day looks at Dec 25 only', () => {
		expect(isWhite([0, 1, 0], 'christmas_day', 1)).toBe(true);
		expect(isWhite([5, 0, 5], 'christmas_day', 1)).toBe(false);
		expect(isWhite([5, N, 5], 'christmas_day', 1)).toBe(null);
	});

	it('all_three_days needs every day', () => {
		expect(isWhite([1, 2, 3], 'all_three_days', 1)).toBe(true);
		expect(isWhite([1, 0, 3], 'all_three_days', 1)).toBe(false);
		expect(isWhite([N, 0, 3], 'all_three_days', 1)).toBe(null);
		expect(isWhite([N, 4, 3], 'all_three_days', 1)).toBe(null);
	});

	it('any_day needs one of the days, and all three to be known', () => {
		expect(isWhite([0, 0, 1], 'any_day', 1)).toBe(true);
		expect(isWhite([0, 0, 0], 'any_day', 1)).toBe(false);
		expect(isWhite([N, N, 2], 'any_day', 1)).toBe(null);
		expect(isWhite([N, 0, 0], 'any_day', 1)).toBe(null);
	});

	it('honours the threshold, with 254 meaning at least 254 cm', () => {
		expect(isWhite([0, 4, 0], 'christmas_day', 5)).toBe(false);
		expect(isWhite([0, 5, 0], 'christmas_day', 5)).toBe(true);
		expect(isWhite([0, 254, 0], 'christmas_day', 254)).toBe(true);
	});
});

/** 1 × 1-cell tile over 1950–1959 with Dec 24/25/26 depths given per year. */
function history(days: (number | null)[][]) {
	const header = [0x57, 0x58, 0x50, 0x31, 0x9e, 0x07, days.length, 0, 1, 0, 1, 0, 3, 0, 0, 0];
	const body = days.flat().map((d) => (d === null ? 255 : d));
	return cellHistory(decodePointTile(new Uint8Array([...header, ...body, 0])), 0, 0);
}

// 1950…1959: W G W W G (nodata) W G G W on Dec 25
const TEN = history([
	[0, 10, 0],
	[0, 0, 0],
	[3, 2, 1],
	[0, 30, 0],
	[0, 0, 0],
	[N, N, N],
	[8, 8, 8],
	[0, 0, 0],
	[2, 0, 0],
	[0, 4, 9]
]);

describe('yearStrip', () => {
	it('labels each year white, green or nodata with the depth that counts', () => {
		const strip = yearStrip(TEN, 'christmas_day', 1);
		expect(strip.map((s) => s.state)).toEqual<YearState[]>([
			'white',
			'green',
			'white',
			'white',
			'green',
			'nodata',
			'white',
			'green',
			'green',
			'white'
		]);
		expect(strip[0]).toEqual({ year: 1950, state: 'white', depth: 10, capped: false });
		expect(strip[5].depth).toBeNull();
	});

	it('uses the mean of the three days as depth for the multi-day definitions', () => {
		const strip = yearStrip(TEN, 'all_three_days', 1);
		expect(strip[2]).toEqual({ year: 1952, state: 'white', depth: 2, capped: false });
		expect(strip[9].depth).toBeCloseTo(13 / 3, 9);
	});
});

describe('probability', () => {
	const strip = yearStrip(TEN, 'christmas_day', 1);

	it('is the share of white years among years with data', () => {
		// 5 white of 9 valid years
		const p = probability(strip, 1950, 1959);
		expect(p.nValid).toBe(9);
		expect(p.nWhite).toBe(5);
		expect(p.p).toBeCloseTo(55.5556, 3);
	});

	it('reports the mean snow depth in white years', () => {
		// white years Dec 25 depths: 10, 2, 30, 8, 4
		expect(probability(strip, 1950, 1959).meanDepthWhite).toBeCloseTo(10.8, 9);
	});

	it('respects the window and returns null without valid years', () => {
		expect(probability(strip, 1950, 1951).p).toBe(50);
		const empty = probability(strip, 1955, 1955);
		expect(empty.p).toBeNull();
		expect(empty.meanDepthWhite).toBeNull();
	});

	it('needs at least 80 % valid years in the window, like the map', () => {
		// 1950–1959 has 9 of 10 valid years (90 %): shown
		expect(probability(strip, 1950, 1959).p).not.toBeNull();
		// 1954–1957 has 3 of 4 valid years (75 %): not enough, but the counts stay
		const thin = probability(strip, 1954, 1957);
		expect(thin.p).toBeNull();
		expect(thin.nValid).toBe(3);
		expect(thin.nWhite).toBe(1);
	});
});

describe('decadeProbabilities', () => {
	it('computes one probability per decade window, oldest first', () => {
		const strip = yearStrip(TEN, 'christmas_day', 1);
		const windows = [
			{ id: '1955_1959', label: '1955–1959', start: 1955, end: 1959, kind: 'decade' as const },
			{ id: '1950_1954', label: '1950–1954', start: 1950, end: 1954, kind: 'decade' as const },
			{ id: '1950_1959', label: 'all', start: 1950, end: 1959, kind: 'full' as const }
		];
		const out = decadeProbabilities(strip, windows);
		expect(out.map((d) => d.window.id)).toEqual(['1950_1954', '1955_1959']);
		expect(out[0].p).toBe(60); // W G W W G
		expect(out[1].p).toBe(50); // (nodata) W G G W
	});
});

describe('olsTrend', () => {
	it('fits a known line: white years only at the end gives a positive slope', () => {
		// x = 0…9, y = 0 0 0 0 0 100 100 100 100 100 → Sxy = 1250, Sxx = 82.5 → slope 15.15 pp/yr
		const strip = Array.from({ length: 10 }, (_, k) => ({
			year: 2000 + k,
			state: (k >= 5 ? 'white' : 'green') as YearState,
			depth: null,
			capped: false
		}));
		const t = olsTrend(strip, 2000, 2009)!;
		expect(t.n).toBe(10);
		expect(t.perDecade).toBeCloseTo(151.515, 2);
		expect(t.pValue).toBeLessThan(0.05);
		expect(t.low90).toBeLessThan(t.perDecade);
		expect(t.high90).toBeGreaterThan(t.perDecade);
	});

	it('gives a zero slope and p = 1 for an alternating series', () => {
		// W G W G … over 1950–1953 and G W G W … over 1954–1957: symmetric, slope 0
		const states: YearState[] = [
			'white',
			'green',
			'white',
			'green',
			'green',
			'white',
			'green',
			'white'
		];
		const strip = states.map((state, k) => ({ year: 1950 + k, state, depth: null, capped: false }));
		const t = olsTrend(strip, 1950, 1957)!;
		expect(t.perDecade).toBeCloseTo(0, 9);
		expect(t.pValue).toBeCloseTo(1, 6);
	});

	it('takes the slope from OLS and the p-value from Mann–Kendall with ties correction', () => {
		// x = 0…4, y = 0 0 100 0 100 → OLS slope 20 pp/yr.
		// Mann–Kendall: S = 4; ties: 3 green, 2 white → var = (5·4·15 − (3·2·11 + 2·1·9)) / 18 = 12;
		// z = (S − 1)/√12 = 0.8660; p = erfc(z/√2) = 0.38648
		const states: YearState[] = ['green', 'green', 'white', 'green', 'white'];
		const strip = states.map((state, k) => ({ year: 2000 + k, state, depth: null, capped: false }));
		const t = olsTrend(strip, 2000, 2004)!;
		expect(t.perDecade).toBeCloseTo(200, 9);
		expect(t.pValue).toBeCloseTo(0.38648, 4);
	});

	it('gives the textbook Mann–Kendall p for a step series', () => {
		// 5 green then 5 white: S = 25, var = 91.667, z = 2.5067, p = 0.012186
		const strip = Array.from({ length: 10 }, (_, k) => ({
			year: 2000 + k,
			state: (k >= 5 ? 'white' : 'green') as YearState,
			depth: null,
			capped: false
		}));
		expect(olsTrend(strip, 2000, 2009)!.pValue).toBeCloseTo(0.012186, 5);
	});

	it('gives no trend with fewer than 80 % valid years in the window', () => {
		const strip = Array.from({ length: 10 }, (_, k) => ({
			year: 2000 + k,
			state: (k < 3 ? 'nodata' : k % 2 ? 'white' : 'green') as YearState,
			depth: null,
			capped: false
		}));
		expect(olsTrend(strip, 2000, 2009)).toBeNull();
	});

	it('needs at least three valid years', () => {
		const strip = [
			{ year: 2000, state: 'white' as YearState, depth: 1, capped: false },
			{ year: 2001, state: 'green' as YearState, depth: 0, capped: false }
		];
		expect(olsTrend(strip, 2000, 2001)).toBeNull();
	});

	it('returns a zero-variance fit (all white) as slope 0 with no uncertainty claim', () => {
		const strip = Array.from({ length: 6 }, (_, k) => ({
			year: 2000 + k,
			state: 'white' as YearState,
			depth: 5,
			capped: false
		}));
		const t = olsTrend(strip, 2000, 2005)!;
		expect(t.perDecade).toBe(0);
		expect(t.pValue).toBe(1);
	});
});
