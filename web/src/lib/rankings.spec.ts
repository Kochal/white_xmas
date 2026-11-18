import { describe, expect, it } from 'vitest';
import type { Place } from '#lib/data/places.ts';
import { declines, snowiest } from './rankings';

const place = (name: string, pop: number, p_then: number | null, p_now: number | null): Place => ({
	name,
	ascii: name,
	country: 'XX',
	admin1: '',
	alt: [],
	lat: 0,
	lon: 0,
	pop,
	p_full: null,
	p_then,
	p_now,
	trend: null
});

const PLACES = [
	place('Big snowy', 2_000_000, 60, 50),
	place('Big dry', 3_000_000, 5, 2),
	place('Small snowy', 20_000, 90, 90),
	place('Big falling', 1_500_000, 40, 10),
	place('Big no data', 1_200_000, null, null)
];

describe('rankings', () => {
	it('snowiest: big places by recent probability, without nodata', () => {
		expect(snowiest(PLACES, 1_000_000, 10).map((p) => p.name)).toEqual([
			'Big snowy',
			'Big falling',
			'Big dry'
		]);
	});

	it('declines: biggest drop first, only places that used to be white at least 1 in 10 years', () => {
		expect(declines(PLACES, 1_000_000, 10).map((p) => p.name)).toEqual([
			'Big falling',
			'Big snowy'
		]);
	});
});
