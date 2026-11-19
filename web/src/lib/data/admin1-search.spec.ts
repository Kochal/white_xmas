import { describe, expect, it } from 'vitest';
import type { RegionRow } from './admin1';
import { mergeHits, searchRegions } from './admin1-search';
import type { Place } from './places';
import type { SearchHit } from './search';

const row = (id: string, name: string, country: string, area = 20000): RegionRow => ({
	num: 0,
	id,
	name,
	country,
	lon: 0,
	lat: 0,
	area_km2: area,
	flags: [],
	p_full: null,
	p_then: null,
	p_now: null,
	change: null,
	trend: null,
	trend_p: null,
	p_now_pop: null,
	p_then_raw: null,
	p_now_raw: null,
	gwl: {}
});

const ROWS = [
	row('DE-BY', 'Bavaria', 'DEU', 70550),
	row('AT-7', 'Tyrol', 'AUT', 12687),
	row('IT-32', 'Trentino-Alto Adige', 'ITA', 13607),
	row('CA-ON', 'Ontario', 'CAN', 1_000_000),
	row('US-OH', 'Ohio', 'USA', 116000),
	row('DE-NW', 'North Rhine-Westphalia', 'DEU', 34000),
	row('CA-NB', 'New Brunswick', 'CAN', 72000),
	row('GB-ENG', 'England', 'GBR', 130000),
	row('DE-HB', 'Bremen', 'DEU', 419)
];
const COUNTRIES = {
	DEU: { name: 'Germany' },
	AUT: { name: 'Austria' },
	ITA: { name: 'Italy' },
	CAN: { name: 'Canada' },
	USA: { name: 'United States of America' },
	GBR: { name: 'United Kingdom' }
};
const ALPHAS = ['One', 'Two', 'Three'].map((n, k) => row(`AL-${k}`, `Alpha ${n}`, 'DEU'));
const ids = (q: string, limit = 4) => searchRegions(ROWS, COUNTRIES, q, limit).map((h) => h.row.id);

describe('searchRegions', () => {
	it('finds by exact name, prefix and ignoring case and accents', () => {
		expect(ids('bavaria')).toEqual(['DE-BY']);
		expect(ids('TYR')).toEqual(['AT-7']);
		expect(ids('Bavária')).toEqual(['DE-BY']);
	});

	it('finds a word inside a name, and a longer substring', () => {
		expect(ids('rhine')).toEqual(['DE-NW']);
		expect(ids('westph')).toEqual(['DE-NW']);
		expect(ids('runsw')).toEqual(['CA-NB']);
	});

	it('uses the country name as extra words, for several-word queries', () => {
		expect(ids('ontario canada')).toEqual(['CA-ON']);
		expect(ids('new canada')).toEqual(['CA-NB']);
		expect(ids('bremen germany')).toEqual(['DE-HB']);
	});

	it('ranks exact before prefix before word match, with the bigger region first on a tie', () => {
		const rows = [
			row('X-1', 'Ohio Valley', 'USA', 100),
			row('X-2', 'Ohio', 'USA', 100),
			row('X-3', 'South Ohio', 'USA', 100)
		];
		const hits = searchRegions(rows, COUNTRIES, 'ohio', 5).map((h) => h.row.id);
		expect(hits).toEqual(['X-2', 'X-1', 'X-3']);
	});

	it('returns nothing for a single letter or a miss, and respects the limit', () => {
		expect(ids('b')).toEqual([]);
		expect(ids('zzzzzz')).toEqual([]);
		expect(ids('e', 1)).toEqual([]);
		expect(searchRegions(ALPHAS, COUNTRIES, 'alpha', 2)).toHaveLength(2);
	});

	it('adds the country name to each hit', () => {
		expect(searchRegions(ROWS, COUNTRIES, 'ohio', 1)[0].countryName).toBe(
			'United States of America'
		);
	});
});

const place = (name: string): Place => ({
	name,
	ascii: name,
	country: 'DE',
	admin1: '',
	alt: [],
	lat: 0,
	lon: 0,
	pop: 1000,
	p_full: null,
	p_then: null,
	p_now: null,
	trend: null
});
const pHit = (name: string, score: number): SearchHit => ({
	place: place(name),
	score,
	matched: name
});

describe('mergeHits', () => {
	const regions = searchRegions(ALPHAS, COUNTRIES, 'alpha', 5); // several matches

	it('orders places and regions by score', () => {
		const m = mergeHits(
			[pHit('Bavaria village', 70), pHit('Bavar', 50)],
			searchRegions(ROWS, COUNTRIES, 'bavaria'),
			8
		);
		expect(m.map((h) => h.kind)).toEqual(['region', 'place', 'place']);
	});

	it('keeps room for at least two regions behind a wall of places', () => {
		const places = Array.from({ length: 8 }, (_, k) => pHit(`Place ${k}`, 90 - k));
		const m = mergeHits(places, regions, 8, 2);
		expect(m).toHaveLength(8);
		expect(m.filter((h) => h.kind === 'region')).toHaveLength(2);
		// the places that stay are the best ones
		expect(m.filter((h) => h.kind === 'place').map((h) => h.score)).toEqual([
			90, 89, 88, 87, 86, 85
		]);
	});

	it('does not invent regions, and passes through a short list', () => {
		const m = mergeHits([pHit('A', 60)], [], 8, 2);
		expect(m).toHaveLength(1);
		expect(mergeHits([], [], 8)).toEqual([]);
	});
});
