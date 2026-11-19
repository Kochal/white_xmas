import { describe, expect, it } from 'vitest';
import { parseManifest } from '#lib/data/manifest.ts';
import {
	availableKinds,
	futureModes,
	normalizeSelection,
	periodOptions,
	resolveLayer,
	warmingLevelNote
} from './layers';

const layer = (o: Record<string, unknown>) => ({
	url: `tiles/${o.id}.pmtiles`,
	colormap: 'probability',
	...o
});

function manifest(projections = true) {
	return parseManifest({
		schema_version: 1,
		data_version: 't',
		built: '',
		build_hash: '',
		years: { first: 1950, last: 2025 },
		threshold_cm: 1,
		attribution: '',
		definitions: [
			{ id: 'christmas_day', label: 'Dec 25', short: 'Dec 25', description: '', default: true },
			{ id: 'all_three_days', label: 'DWD', short: 'Dec 24–26', description: '' }
		],
		windows: [
			{ id: '1950_2025', label: '1950–2025', start: 1950, end: 2025, kind: 'full' },
			{ id: '1961_1990', label: '1961–1990', start: 1961, end: 1990, kind: 'normal' },
			{ id: '1996_2025', label: '1996–2025', start: 1996, end: 2025, kind: 'normal' },
			{ id: '2006_2015', label: '2006–2015', start: 2006, end: 2015, kind: 'decade' },
			{ id: '2016_2025', label: '2016–2025', start: 2016, end: 2025, kind: 'decade' }
		],
		layers: [
			layer({ id: 'p1', kind: 'probability', definition: 'christmas_day', window: '2006_2015' }),
			layer({ id: 'p2', kind: 'probability', definition: 'christmas_day', window: '1996_2025' }),
			layer({ id: 'p3', kind: 'probability', definition: 'christmas_day', window: '1950_2025' }),
			layer({ id: 'p4', kind: 'probability', definition: 'christmas_day', window: '2016_2025' }),
			layer({ id: 'p5', kind: 'probability', definition: 'all_three_days', window: '1996_2025' }),
			layer({
				id: 'c1',
				kind: 'change',
				definition: 'christmas_day',
				from: '1961_1990',
				to: '1996_2025',
				colormap: 'change'
			}),
			layer({
				id: 't1',
				kind: 'trend',
				definition: 'christmas_day',
				window: '1950_2025',
				colormap: 'trend'
			}),
			layer({ id: 'f2', kind: 'projection', definition: 'christmas_day', warming_level: 2.0 }),
			layer({ id: 'f15', kind: 'projection', definition: 'christmas_day', warming_level: 1.5 }),
			layer({
				id: 'fc2',
				kind: 'projection_change',
				definition: 'christmas_day',
				warming_level: 2.0,
				colormap: 'change',
				hatch_disagreement: true
			})
		],
		colormaps: {},
		points: { index: 'points/index.json', tile_deg: 5, format: 'wx-points-v1' },
		projections: projections
			? {
					available: true,
					warming_levels: [
						{ gwl: 1.5, label: '+1.5 °C', approx: '2030s' },
						{ gwl: 2.0, label: '+2 °C', approx: '2050s' },
						{
							gwl: 3.0,
							label: '+3 °C',
							approx: 'not reached under SSP2-4.5 by most models'
						}
					]
				}
			: { available: false },
		places: 'places.json',
		regions: 'regions.json'
	});
}

describe('availableKinds', () => {
	it('offers Future only when the manifest says projections are available', () => {
		expect(availableKinds(manifest(true))).toEqual([
			'probability',
			'change',
			'trend',
			'projection'
		]);
		expect(availableKinds(manifest(false))).toEqual(['probability', 'change', 'trend']);
	});
});

describe('periodOptions', () => {
	it('lists probability windows as full period, normals, then decades newest first', () => {
		const opts = periodOptions(manifest(), 'probability', 'christmas_day');
		expect(opts.map((o) => o.value)).toEqual(['1950_2025', '1996_2025', '2016_2025', '2006_2015']);
		expect(opts[0].label).toBe('1950–2025');
	});

	it('labels change layers as "then vs now"', () => {
		const opts = periodOptions(manifest(), 'change', 'christmas_day');
		expect(opts).toEqual([{ value: '1961_1990__1996_2025', label: '1961–1990 → 1996–2025' }]);
	});

	it('lists warming levels that have a layer, in manifest order', () => {
		const opts = periodOptions(manifest(), 'projection', 'christmas_day');
		// contract v1.3: approx may be long, so the option shows the label only
		expect(opts).toEqual([
			{ value: '1.5', label: '+1.5 °C' },
			{ value: '2', label: '+2 °C' }
		]);
		expect(warmingLevelNote(manifest(), '2')).toBe('2050s');
		expect(warmingLevelNote(manifest(), '3')).toBe('not reached under SSP2-4.5 by most models');
	});

	it('is empty when a definition has no layer of that kind', () => {
		expect(periodOptions(manifest(), 'trend', 'all_three_days')).toEqual([]);
	});
});

describe('normalizeSelection + resolveLayer', () => {
	it('defaults to the default definition, probability and the latest 30-year normal', () => {
		const m = manifest();
		const sel = normalizeSelection(m, {});
		expect(sel).toEqual({ definition: 'christmas_day', kind: 'probability', period: '1996_2025' });
		expect(resolveLayer(m, sel)?.id).toBe('p2');
	});

	it('snaps an unavailable period to the first available one', () => {
		const m = manifest();
		const sel = normalizeSelection(m, { kind: 'change', period: '1950_2025' });
		expect(sel.period).toBe('1961_1990__1996_2025');
		expect(resolveLayer(m, sel)?.id).toBe('c1');
	});

	it('keeps a definition without map layers but resolves no layer (the panel still works)', () => {
		const m = manifest();
		const sel = normalizeSelection(m, { definition: 'all_three_days', kind: 'trend' });
		expect(sel.definition).toBe('all_three_days');
		expect(resolveLayer(m, sel)).toBeNull();
	});

	it('drops unknown definitions and kinds, and Future when projections are off', () => {
		const sel = normalizeSelection(manifest(false), { definition: 'nope', kind: 'projection' });
		expect(sel.definition).toBe('christmas_day');
		expect(sel.kind).toBe('probability');
	});

	it('resolves a projection layer by warming level', () => {
		const m = manifest();
		const sel = normalizeSelection(m, { kind: 'projection', period: '2' });
		expect(resolveLayer(m, sel)?.id).toBe('f2');
	});
});

describe('Future: change vs today (contract v1.2)', () => {
	it('offers both Future views when both layer kinds exist, none when projections are off', () => {
		expect(futureModes(manifest(true))).toEqual(['projection', 'projection_change']);
		expect(futureModes(manifest(false))).toEqual([]);
		// projection_change is a view under the Future tab, not a tab of its own
		expect(availableKinds(manifest(true))).not.toContain('projection_change');
	});

	it('offers the Future tab only for definitions with projection layers', () => {
		expect(availableKinds(manifest(true), 'christmas_day')).toContain('projection');
		expect(availableKinds(manifest(true), 'all_three_days')).not.toContain('projection');
	});

	it('resolves the change-vs-today layer for the same warming level', () => {
		const m = manifest();
		const sel = normalizeSelection(m, { kind: 'projection_change', period: '2' });
		expect(sel.kind).toBe('projection_change');
		expect(resolveLayer(m, sel)?.id).toBe('fc2');
	});

	it('snaps to a warming level that has a change layer', () => {
		const m = manifest();
		const sel = normalizeSelection(m, { kind: 'projection_change', period: '1.5' });
		expect(sel.period).toBe('2');
		expect(periodOptions(m, 'projection_change', 'christmas_day')).toEqual([
			{ value: '2', label: '+2 °C' }
		]);
	});

	it('falls back to the projected probability for a definition without change layers', () => {
		const m = manifest();
		const sel = normalizeSelection(m, { kind: 'projection_change', definition: 'all_three_days' });
		expect(sel.kind).toBe('probability');
	});

	it('ignores projection_change when projections are not available', () => {
		const sel = normalizeSelection(manifest(false), { kind: 'projection_change' });
		expect(sel.kind).toBe('probability');
	});
});
