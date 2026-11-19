import { describe, expect, it } from 'vitest';
import {
	parseRegionHash,
	parseUrlState,
	regionHash,
	serializeUrl,
	serializeUrlState
} from './url-state';

describe('URL state', () => {
	it('round-trips view, selection and the selected place', () => {
		const state = {
			view: { zoom: 5.25, lat: 48.1, lon: 11.5 },
			selection: {
				definition: 'christmas_day',
				threshold: 'raw',
				kind: 'change' as const,
				period: '1961_1990__1996_2025'
			},
			at: { lat: 48.14, lon: 11.58 },
			place: 'Munich'
		};
		const qs = serializeUrlState(state);
		expect(qs).toBe(
			'?def=christmas_day&th=raw&layer=change&period=1961_1990__1996_2025&map=5.25%2F48.1000%2F11.5000&at=48.1400%2C11.5800&place=Munich'
		);
		expect(parseUrlState(new URLSearchParams(qs))).toEqual(state);
	});

	it('ignores malformed values instead of failing', () => {
		const s = parseUrlState(new URLSearchParams('map=abc&at=95,10&layer=bogus&def=x'));
		expect(s.view).toBeUndefined();
		expect(s.at).toBeUndefined();
		expect(s.selection.kind).toBeUndefined();
		expect(s.selection.definition).toBe('x'); // validated later against the manifest
	});

	it('leaves out what is not set', () => {
		expect(serializeUrlState({ selection: {} })).toBe('');
	});
});

describe('URL state: states and provinces', () => {
	it('reads #/region/<id> and switches the borders layer on', () => {
		const s = parseUrlState(new URLSearchParams(''), '#/region/DE-BY');
		expect(s.region).toBe('DE-BY');
		expect(s.regions).toBe(true);
	});

	it('lets a region link win over a point', () => {
		const s = parseUrlState(new URLSearchParams('at=48.1,11.5&place=Munich'), '#/region/AT-7');
		expect(s.region).toBe('AT-7');
		expect(s.at).toBeUndefined();
		expect(s.place).toBeUndefined();
	});

	it('reads ?regions=1 without a region', () => {
		const s = parseUrlState(new URLSearchParams('regions=1'));
		expect(s.regions).toBe(true);
		expect(s.region).toBeUndefined();
	});

	it('ignores malformed hashes', () => {
		for (const h of [
			'',
			'#',
			'#/region/',
			'#/region/a/b',
			'#/place/DE-BY',
			'#/region/%E0%A4',
			'#/region/<script>',
			'#/region/' + 'A'.repeat(40)
		])
			expect(parseRegionHash(h), h).toBeUndefined();
		expect(parseRegionHash('#/region/DE-BY/')).toBe('DE-BY');
		expect(parseRegionHash('#/region/US-DC')).toBe('US-DC');
	});

	it('serializes the borders flag and the hash, and round-trips', () => {
		const state = { selection: {}, regions: true, region: 'DE-BY' };
		expect(serializeUrlState(state)).toBe('?regions=1');
		expect(serializeUrl(state)).toBe('?regions=1#/region/DE-BY');
		expect(parseUrlState(new URLSearchParams('regions=1'), '#/region/DE-BY')).toEqual(state);
		expect(serializeUrl({ selection: {} })).toBe('');
	});

	it('never writes an unsafe region id into the URL', () => {
		expect(regionHash('a b/c')).toBe('');
		expect(regionHash(undefined)).toBe('');
	});
});
