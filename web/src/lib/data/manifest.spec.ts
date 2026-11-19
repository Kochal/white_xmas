import { describe, expect, it } from 'vitest';
import {
	ManifestError,
	defaultDefinition,
	defaultThreshold,
	definitionText,
	thresholdById,
	thresholdNote,
	thresholdShortLabel,
	findLayer,
	loadManifest,
	parseManifest,
	type Manifest
} from './manifest';

function sampleManifest(): Record<string, unknown> {
	return {
		schema_version: 1,
		data_version: '2026.1',
		built: '2026-11-20T12:00:00Z',
		build_hash: 'abc123',
		years: { first: 1950, last: 2025 },
		threshold_cm: 1,
		attribution: 'Contains modified Copernicus Climate Change Service information.',
		definitions: [
			{
				id: 'christmas_day',
				label: 'Snow on Christmas Day',
				short: 'Dec 25',
				description: '…',
				default: true
			},
			{
				id: 'all_three_days',
				label: 'Snow on all three days (DWD)',
				short: 'Dec 24–26',
				description: '…'
			}
		],
		windows: [
			{ id: '1950_2025', label: '1950–2025', start: 1950, end: 2025, kind: 'full' },
			{ id: '1996_2025', label: '1996–2025', start: 1996, end: 2025, kind: 'normal' }
		],
		layers: [
			{
				id: 'prob__christmas_day__1996_2025',
				kind: 'probability',
				definition: 'christmas_day',
				window: '1996_2025',
				url: 'tiles/prob__christmas_day__1996_2025.pmtiles',
				colormap: 'probability'
			},
			{
				id: 'change__christmas_day__1961_1990__1996_2025',
				kind: 'change',
				definition: 'christmas_day',
				from: '1961_1990',
				to: '1996_2025',
				url: 'tiles/c.pmtiles',
				colormap: 'change'
			}
		],
		colormaps: {
			probability: {
				unit: '%',
				domain: [0, 100],
				stops: [
					[0, '#ffffff'],
					[100, '#000080']
				]
			}
		},
		glacier_style: 'hatched',
		points: { index: 'points/index.json', tile_deg: 5, format: 'wx-points-v1' },
		places: 'places.json',
		regions: 'regions.json'
	};
}

describe('parseManifest', () => {
	it('accepts a contract-shaped manifest and treats missing projections as unavailable', () => {
		const m = parseManifest(sampleManifest());
		expect(m.data_version).toBe('2026.1');
		expect(m.projections.available).toBe(false);
		expect(m.projections.warming_levels).toEqual([]);
	});

	it('rejects an unknown schema version with a readable error', () => {
		expect(() => parseManifest({ ...sampleManifest(), schema_version: 2 })).toThrow(
			/schema_version 2/
		);
	});

	it('rejects a manifest without definitions or layers', () => {
		expect(() => parseManifest({ ...sampleManifest(), definitions: [] })).toThrow(ManifestError);
		expect(() => parseManifest({ ...sampleManifest(), layers: 'nope' })).toThrow(ManifestError);
	});

	it('keeps v1.2 projection_change layers with their hatch flag', () => {
		const raw = sampleManifest();
		(raw.layers as unknown[]).push({
			id: 'projchange__christmas_day__gwl2.0',
			kind: 'projection_change',
			definition: 'christmas_day',
			warming_level: 2.0,
			url: 'tiles/pc.pmtiles',
			colormap: 'change',
			hatch_disagreement: true
		});
		const l = parseManifest(raw).layers.find((x) => x.kind === 'projection_change');
		expect(l).toMatchObject({ warming_level: 2, hatch_disagreement: true });
	});

	it('ignores layers of kinds it does not know, so newer pipelines do not break the site', () => {
		const raw = sampleManifest();
		(raw.layers as unknown[]).push({ id: 'x', kind: 'snowfall', url: 'tiles/x.pmtiles' });
		expect(parseManifest(raw).layers.map((l) => l.id)).toEqual([
			'prob__christmas_day__1996_2025',
			'change__christmas_day__1961_1990__1996_2025'
		]);
	});
});

describe('manifest helpers', () => {
	const m: Manifest = parseManifest(sampleManifest());

	it('finds the default definition, or the first one when none is flagged', () => {
		expect(defaultDefinition(m).id).toBe('christmas_day');
		const noDefault = parseManifest({
			...sampleManifest(),
			definitions: [{ id: 'any_day', label: 'a', short: 'a', description: 'a' }]
		});
		expect(defaultDefinition(noDefault).id).toBe('any_day');
	});

	it('finds layers by kind, definition and window', () => {
		expect(
			findLayer(m, { kind: 'probability', definition: 'christmas_day', window: '1996_2025' })?.id
		).toBe('prob__christmas_day__1996_2025');
		expect(
			findLayer(m, { kind: 'probability', definition: 'christmas_day', window: '1950_2025' })
		).toBeUndefined();
		expect(findLayer(m, { kind: 'change', definition: 'christmas_day' })?.id).toBe(
			'change__christmas_day__1961_1990__1996_2025'
		);
	});
});

describe('threshold', () => {
	it('reads threshold_cm from the manifest and explains a calibrated threshold', () => {
		const plain = parseManifest(sampleManifest());
		expect(plain.threshold_cm).toBe(1);
		expect(thresholdNote(plain)).toBeNull();
		const calibrated = parseManifest({
			...sampleManifest(),
			threshold_cm: 4,
			station_equivalent_cm: 1
		});
		expect(calibrated.threshold_cm).toBe(4);
		expect(thresholdNote(calibrated)).toBe(
			'Calibrated: 4 cm in ERA5-Land ≈ 1 cm at a weather station.'
		);
	});
});

describe('thresholds (contract v1.5)', () => {
	const V15 = {
		threshold_cm: 5,
		station_equivalent_cm: 1,
		thresholds: [
			{
				id: 'calibrated',
				cm: 5,
				default: true,
				station_equivalent_cm: 1,
				label: 'Calibrated to weather stations',
				description: 'At least 5 cm of snow in ERA5-Land, which matches at least 1 cm at stations.'
			},
			{
				id: 'raw',
				cm: 1,
				label: 'Raw ERA5-Land, at least 1 cm',
				description: 'At least 1 cm of snow in ERA5-Land as published.'
			}
		]
	};

	it('reads both thresholds and tags layers without a threshold with the default', () => {
		const raw: Record<string, unknown> = { ...sampleManifest(), ...V15 };
		(raw.layers as Record<string, unknown>[]).push({
			id: 'prob__christmas_day__1996_2025__raw',
			kind: 'probability',
			definition: 'christmas_day',
			window: '1996_2025',
			url: 'tiles/r.pmtiles',
			colormap: 'probability',
			threshold: 'raw'
		});
		const m = parseManifest(raw);
		expect(m.thresholds.map((t) => t.id)).toEqual(['calibrated', 'raw']);
		expect(defaultThreshold(m).cm).toBe(5);
		expect(m.layers.map((l) => l.threshold)).toEqual(['calibrated', 'calibrated', 'raw']);
		expect(thresholdById(m, 'raw').cm).toBe(1);
		expect(thresholdById(m, 'nope').id).toBe('calibrated');
		expect(thresholdShortLabel(m.thresholds[0])).toBe('Calibrated to stations');
		expect(thresholdShortLabel(m.thresholds[1])).toBe('Raw ERA5-Land (1 cm)');
		expect(thresholdNote(m, m.thresholds[0])).toBe(
			'Calibrated: 5 cm in ERA5-Land ≈ 1 cm at a weather station.'
		);
		expect(thresholdNote(m, m.thresholds[1])).toBeNull();
	});

	it('rewrites the number in definition texts for another threshold', () => {
		const m = parseManifest({ ...sampleManifest(), ...V15 });
		const d = {
			id: 'christmas_day',
			label: 'x',
			short: 'x',
			description: 'Snow depth on 25 December is at least 5 cm.'
		};
		expect(definitionText(m, d, m.thresholds[0])).toBe(d.description);
		expect(definitionText(m, d, m.thresholds[1])).toBe(
			'Snow depth on 25 December is at least 1 cm.'
		);
		// numbers that merely contain the default don't change
		const e = { ...d, description: 'At least 5 cm; 15 cm and 25 December stay.' };
		expect(definitionText(m, e, m.thresholds[1])).toBe(
			'At least 1 cm; 15 cm and 25 December stay.'
		);
	});

	it('builds a single default threshold for v1.4 manifests', () => {
		const m = parseManifest({ ...sampleManifest(), threshold_cm: 4, station_equivalent_cm: 1 });
		expect(m.thresholds).toHaveLength(1);
		expect(defaultThreshold(m)).toMatchObject({ cm: 4, station_equivalent_cm: 1, default: true });
		expect(m.layers.every((l) => l.threshold === 'default')).toBe(true);
	});
});

describe('loadManifest', () => {
	it('fetches manifest.json under the data base URL', async () => {
		const seen: string[] = [];
		const fetchFn = (async (url: string) => {
			seen.push(url);
			return new Response(JSON.stringify(sampleManifest()));
		}) as typeof fetch;
		const m = await loadManifest('/white_xmas/data', fetchFn);
		expect(seen).toEqual(['/white_xmas/data/manifest.json']);
		expect(m.years).toEqual({ first: 1950, last: 2025 });
	});

	it('reports a missing manifest clearly', async () => {
		const fetchFn = (async () => new Response('nope', { status: 404 })) as unknown as typeof fetch;
		await expect(loadManifest('/data', fetchFn)).rejects.toThrow(/404/);
	});
});
