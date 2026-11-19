/**
 * The states-and-provinces layer on the map: faint borders at world zoom, labels from a zoom
 * that depends on the region's size, hover and selected states. Pure builders only (the
 * MapView adds them), so they are unit-tested.
 */
import type { LayerSpecification } from 'maplibre-gl';
import type { RegionRow } from '#lib/data/admin1.ts';

export const REGIONS_SOURCE = 'wx-regions';
export const LABELS_SOURCE = 'wx-region-labels';
export const FILL_LAYER = 'wx-regions-fill';
export const LINE_LAYER = 'wx-regions-line';
export const SELECTED_FILL = 'wx-regions-selected-fill';
export const SELECTED_LINE = 'wx-regions-selected-line';
export const LABEL_PREFIX = 'wx-regions-label-';

/** The parts of a basemap style layer that tell a state border or name from the rest. */
export interface StyleLayerInfo {
	id: string;
	type: string;
	'source-layer'?: string;
	filter?: unknown;
}

/**
 * OpenFreeMap's own state borders and state names. They are hidden while this layer is on, to
 * avoid every border and name twice. The light and dark styles name them differently
 * (`boundary_3` / `label_state` and `boundary_state` / `place_state`), so layers are found by
 * what they draw: lines of the `boundary` source layer filtered to admin level 3 or 4, and
 * symbols of the `place` source layer filtered to class "state". Country borders (level 2)
 * and country, city and town names are not matched.
 */
export function stateLayerIds(layers: StyleLayerInfo[]): string[] {
	return layers
		.filter((l) => {
			const filter = JSON.stringify(l.filter ?? null);
			if (l.type === 'line' && l['source-layer'] === 'boundary')
				return /\["get","admin_level"\],[34]\]/.test(filter);
			if (l.type === 'symbol' && l['source-layer'] === 'place')
				return /\["==",\["get","class"\],"state"\]/.test(filter);
			return false;
		})
		.map((l) => l.id);
}

/** Zoom from which a region of a given area is labelled: big ones early, small ones late. */
export const LABEL_MIN_ZOOM = [3.2, 4.4, 5.6, 6.8] as const;

/** Size class 0 (largest) to 3 (smallest) by polygon area. */
export function labelClass(areaKm2: number | null): 0 | 1 | 2 | 3 {
	const a = areaKm2 ?? 0;
	if (a > 400_000) return 0;
	if (a > 60_000) return 1;
	if (a > 12_000) return 2;
	return 3;
}

export interface LabelCollection {
	type: 'FeatureCollection';
	features: {
		type: 'Feature';
		properties: { id: string; name: string; cls: number };
		geometry: { type: 'Point'; coordinates: [number, number] };
	}[];
}

/** Label points from the index rows: a point inside each region, named. */
export function labelCollection(rows: RegionRow[]): LabelCollection {
	return {
		type: 'FeatureCollection',
		features: rows.map((r) => ({
			type: 'Feature',
			properties: { id: r.id, name: r.name, cls: labelClass(r.area_km2) },
			geometry: { type: 'Point', coordinates: [r.lon, r.lat] }
		}))
	};
}

export interface RegionColors {
	line: string;
	text: string;
	halo: string;
	accent: string;
}

export const LIGHT: RegionColors = {
	line: '#46556b',
	text: '#2b3647',
	halo: 'rgba(255,255,255,0.85)',
	accent: '#1f5fae'
};
export const DARK: RegionColors = {
	line: '#b9c6da',
	text: '#dbe4f1',
	halo: 'rgba(15,20,28,0.85)',
	accent: '#8db6ee'
};

/**
 * Layers in drawing order: invisible-until-hovered fills (they also take the clicks),
 * borders, the selected region's tint and outline, then labels by size class.
 * `glyphs` is false when the style has no fonts (the plain fallback background): no labels then.
 */
export function regionLayers(colors: RegionColors, glyphs: boolean): LayerSpecification[] {
	const layers: LayerSpecification[] = [
		{
			id: FILL_LAYER,
			type: 'fill',
			source: REGIONS_SOURCE,
			paint: {
				'fill-color': colors.accent,
				// a near-zero base keeps every region hit-testable for clicks
				'fill-opacity': ['case', ['boolean', ['feature-state', 'hover'], false], 0.16, 0.01]
			}
		},
		{
			id: LINE_LAYER,
			type: 'line',
			source: REGIONS_SOURCE,
			layout: { 'line-join': 'round' },
			paint: {
				'line-color': colors.line,
				// faint at world zoom, firmer when zoomed in
				'line-opacity': ['interpolate', ['linear'], ['zoom'], 1, 0.1, 3, 0.16, 5, 0.38, 7, 0.65],
				'line-width': ['interpolate', ['linear'], ['zoom'], 1, 0.25, 4, 0.6, 8, 1.4]
			}
		},
		{
			id: SELECTED_FILL,
			type: 'fill',
			source: REGIONS_SOURCE,
			filter: ['==', ['get', 'id'], ''],
			paint: { 'fill-color': colors.accent, 'fill-opacity': 0.12 }
		},
		{
			id: SELECTED_LINE,
			type: 'line',
			source: REGIONS_SOURCE,
			filter: ['==', ['get', 'id'], ''],
			layout: { 'line-join': 'round' },
			paint: { 'line-color': colors.accent, 'line-width': 2.6 }
		}
	];
	if (glyphs)
		LABEL_MIN_ZOOM.forEach((minzoom, cls) =>
			layers.push({
				id: `${LABEL_PREFIX}${cls}`,
				type: 'symbol',
				source: LABELS_SOURCE,
				minzoom,
				filter: ['==', ['get', 'cls'], cls],
				layout: {
					'text-field': ['get', 'name'],
					'text-font': ['Noto Sans Regular'],
					'text-size': ['interpolate', ['linear'], ['zoom'], 3, 10, 8, 13],
					'text-max-width': 7,
					'text-padding': 4,
					'text-allow-overlap': false
				},
				paint: {
					'text-color': colors.text,
					'text-halo-color': colors.halo,
					'text-halo-width': 1.3
				}
			})
		);
	return layers;
}

/** The layers that follow the "show borders" toggle (the selected outline stays). */
export function toggledLayerIds(layers: { id: string }[]): string[] {
	return layers.map((l) => l.id).filter((id) => id !== SELECTED_FILL && id !== SELECTED_LINE);
}

/**
 * A region's bounding box (west, south, east, north) as MapLibre bounds. A region across the
 * antimeridian has east > 180 (Alaska 172.48 to 230.01): MapLibre's fitBounds takes that as it
 * is, so it must not be normalised back into -180..180. Returns null for a malformed box.
 */
export function regionBounds(
	bbox: readonly number[] | null | undefined
): [[number, number], [number, number]] | null {
	if (!bbox || bbox.length !== 4 || bbox.some((v) => !Number.isFinite(v))) return null;
	const [w, s, e, n] = bbox;
	if (e <= w || n < s || s < -90 || n > 90) return null;
	return [
		[w, s],
		[e, n]
	];
}
