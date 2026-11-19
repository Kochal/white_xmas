import { describe, expect, it } from 'vitest';
import type { RegionRow } from '#lib/data/admin1.ts';
import { countryOptions, rankRegions } from './admin1-rankings';

const row = (
	id: string,
	country: string,
	p_then: number | null,
	p_now: number | null,
	flags: string[] = []
): RegionRow => ({
	num: 0,
	id,
	name: id,
	country,
	lon: 0,
	lat: 0,
	area_km2: 1000,
	flags,
	p_full: null,
	p_then,
	p_now,
	change: p_then !== null && p_now !== null ? p_now - p_then : null,
	trend: null,
	trend_p: null,
	p_now_pop: null,
	p_then_raw: null,
	p_now_raw: null,
	gwl: {}
});

const ROWS = [
	row('A', 'AAA', 60, 50),
	row('B', 'AAA', 20, 5),
	row('C', 'BBB', 90, 85),
	row('D', 'BBB', 5, 1), // had < 10 %: not a "decline"
	row('E', 'BBB', null, null, ['no_land']),
	row('F', 'BBB', 95, 40, ['low_res']), // small: world list leaves it out
	row('G', 'AAA', 30, 35) // increase
];

const ids = (r: RegionRow[]) => r.map((x) => x.id);

describe('rankRegions', () => {
	it('snowiest and least snowy skip regions without values', () => {
		expect(ids(rankRegions(ROWS, 'snowiest', {}, 10))).toEqual(['C', 'A', 'G', 'B', 'D']);
		expect(ids(rankRegions(ROWS, 'least_snowy', {}, 10))).toEqual(['D', 'B', 'G', 'A', 'C']);
	});

	it('biggest decline only counts regions that had a white Christmas 1 year in 10', () => {
		expect(ids(rankRegions(ROWS, 'decline', {}, 10))).toEqual(['B', 'A', 'C']);
	});

	it('filters by country, and then lists small regions too', () => {
		expect(ids(rankRegions(ROWS, 'snowiest', { country: 'BBB' }, 10))).toEqual(['C', 'F', 'D']);
		expect(ids(rankRegions(ROWS, 'decline', { country: 'BBB' }, 10))).toEqual(['F', 'C']);
		expect(ids(rankRegions(ROWS, 'snowiest', { country: 'BBB', includeSmall: false }, 10))).toEqual(
			['C', 'D']
		);
	});

	it('can include small regions worldwide, and honours the limit', () => {
		expect(ids(rankRegions(ROWS, 'decline', { includeSmall: true }, 1))).toEqual(['F']);
	});

	it('breaks ties by name', () => {
		const tie = [row('Z', 'X', 50, 40), row('M', 'X', 50, 40)];
		expect(ids(rankRegions(tie, 'snowiest', {}, 5))).toEqual(['M', 'Z']);
	});
});

describe('countryOptions', () => {
	it('lists countries A–Z by name', () => {
		const list = countryOptions({
			DEU: { name: 'Germany', regions: 16 },
			AUT: { name: 'Austria', regions: 9 },
			CIV: { name: 'Côte d’Ivoire', regions: 14 }
		});
		expect(list.map((c) => c.code)).toEqual(['AUT', 'CIV', 'DEU']);
	});
});
