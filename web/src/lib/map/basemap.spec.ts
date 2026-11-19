import { describe, expect, it } from 'vitest';
import type { StyleSpecification } from 'maplibre-gl';
import { slimBasemap, withClimateLayer } from './basemap';

const layer = (id: string, type = 'line') => ({ id, type, source: 'openmaptiles' }) as never;

const POSITRON_LIKE = {
	version: 8,
	sources: { openmaptiles: { type: 'vector', url: 'x' } },
	layers: [
		{ id: 'background', type: 'background' },
		layer('water', 'fill'),
		layer('building', 'fill'),
		layer('aeroway-runway'),
		layer('highway_path'),
		layer('highway_minor'),
		layer('highway_major_inner'),
		layer('highway_motorway_inner'),
		layer('railway_transit'),
		layer('boundary_2'),
		layer('highway-name-major', 'symbol'),
		layer('road_shield_us', 'symbol'),
		layer('airport', 'symbol'),
		layer('label_village', 'symbol'),
		layer('label_city', 'symbol'),
		layer('label_country_1', 'symbol')
	]
} as unknown as StyleSpecification;

describe('slimBasemap', () => {
	it('keeps water, major roads, boundaries and place labels; drops what this map does not need', () => {
		expect(slimBasemap(POSITRON_LIKE).layers.map((l) => l.id)).toEqual([
			'background',
			'water',
			'highway_major_inner',
			'highway_motorway_inner',
			'boundary_2',
			'label_village',
			'label_city',
			'label_country_1'
		]);
	});
});

describe('withClimateLayer', () => {
	it('carries the climate source and layer into the new style, under the boundaries', () => {
		const prev = {
			version: 8,
			sources: { 'wx-layer': { type: 'raster', url: 'pmtiles://a' } },
			layers: [
				{ id: 'background', type: 'background' },
				{ id: 'wx-layer', type: 'raster', source: 'wx-layer' }
			]
		} as unknown as StyleSpecification;
		const next = withClimateLayer(prev, slimBasemap(POSITRON_LIKE), 'wx-layer');
		expect(Object.keys(next.sources)).toEqual(['openmaptiles', 'wx-layer']);
		const ids = next.layers.map((l) => l.id);
		expect(ids.indexOf('wx-layer')).toBe(ids.indexOf('boundary_2') - 1);
	});

	it('leaves the style alone when there is no climate layer yet', () => {
		const prev = { version: 8, sources: {}, layers: [] } as unknown as StyleSpecification;
		const slim = slimBasemap(POSITRON_LIKE);
		expect(withClimateLayer(prev, slim, 'wx-layer').layers).toEqual(slim.layers);
	});
});
