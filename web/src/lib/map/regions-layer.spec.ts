import { describe, expect, it } from 'vitest';
import styles from './style-layers.fixture.json';
import {
	FILL_LAYER,
	LABEL_PREFIX,
	LABEL_MIN_ZOOM,
	labelClass,
	labelCollection,
	regionBounds,
	regionLayers,
	stateLayerIds,
	toggledLayerIds,
	DARK,
	LIGHT,
	SELECTED_FILL,
	SELECTED_LINE,
	type StyleLayerInfo
} from './regions-layer';
import type { RegionRow } from '#lib/data/admin1.ts';

// Copies of the layer lists (id, type, source-layer, filter) of OpenFreeMap's positron and dark
// styles, so the test needs no network.
const light = styles.positron as StyleLayerInfo[];
const dark = styles.dark as StyleLayerInfo[];

describe('stateLayerIds: the basemap draws state borders and names under different ids', () => {
	it("finds the light style's state border and name", () => {
		expect(stateLayerIds(light).sort()).toEqual(['boundary_3', 'label_state']);
	});

	it("finds the dark style's state border and name", () => {
		expect(stateLayerIds(dark).sort()).toEqual(['boundary_state', 'place_state']);
	});

	it('leaves country borders, disputed borders and other labels alone', () => {
		const hidden = new Set([...stateLayerIds(light), ...stateLayerIds(dark)]);
		for (const id of [
			'boundary_2',
			'boundary_disputed',
			'boundary_country_z0-4',
			'boundary_country_z5-',
			'label_country_1',
			'label_city',
			'label_town',
			'label_other',
			'place_city',
			'place_country_major',
			'place_other'
		])
			expect(hidden.has(id), id).toBe(false);
	});

	it('knows nothing it was not told: a style without states hides nothing', () => {
		expect(stateLayerIds([{ id: 'x', type: 'fill', 'source-layer': 'water' }])).toEqual([]);
		expect(stateLayerIds([])).toEqual([]);
	});
});

describe('region layers', () => {
	it('grades labels by area, big regions first', () => {
		expect(labelClass(1_700_000)).toBe(0);
		expect(labelClass(70_000)).toBe(1);
		expect(labelClass(20_000)).toBe(2);
		expect(labelClass(3_000)).toBe(3);
		expect(labelClass(null)).toBe(3);
		expect(LABEL_MIN_ZOOM).toEqual([...LABEL_MIN_ZOOM].sort((a, b) => a - b));
	});

	it('builds one label point per row', () => {
		const rows = [
			{ id: 'DE-BY', name: 'Bavaria', lon: 11.3, lat: 48.9, area_km2: 70550 }
		] as RegionRow[];
		expect(labelCollection(rows).features[0]).toMatchObject({
			properties: { id: 'DE-BY', name: 'Bavaria', cls: 1 },
			geometry: { coordinates: [11.3, 48.9] }
		});
	});

	it('has labels only when the style has fonts, and keeps the selected outline out of the toggle', () => {
		const ids = (glyphs: boolean) => regionLayers(LIGHT, glyphs).map((l) => l.id);
		expect(ids(true).filter((i) => i.startsWith(LABEL_PREFIX))).toHaveLength(4);
		expect(ids(false).filter((i) => i.startsWith(LABEL_PREFIX))).toHaveLength(0);
		const toggled = toggledLayerIds(regionLayers(DARK, true));
		expect(toggled).toContain(FILL_LAYER);
		expect(toggled).not.toContain(SELECTED_FILL);
		expect(toggled).not.toContain(SELECTED_LINE);
	});
});

describe('regionBounds', () => {
	it('passes an ordinary box through', () => {
		expect(regionBounds([8.98, 47.27, 13.84, 50.56])).toEqual([
			[8.98, 47.27],
			[13.84, 50.56]
		]);
	});

	it('keeps east above 180 for regions across the antimeridian (Alaska, Chukotka)', () => {
		expect(regionBounds([172.48, 51.22, 230.01, 71.41])).toEqual([
			[172.48, 51.22],
			[230.01, 71.41]
		]);
		expect(regionBounds([157.69, 61.81, 191.01, 71.6])).toEqual([
			[157.69, 61.81],
			[191.01, 71.6]
		]);
	});

	it('refuses boxes that would make the map jump to the world', () => {
		expect(regionBounds(null)).toBeNull();
		expect(regionBounds([1, 2, 3])).toBeNull();
		expect(regionBounds([10, 0, 5, 1])).toBeNull(); // east <= west
		expect(regionBounds([0, 0, 1, 95])).toBeNull();
		expect(regionBounds([0, 0, Number.NaN, 1])).toBeNull();
	});
});
