/**
 * Basemap handling. The OpenFreeMap styles carry far more than a climate map needs
 * (buildings, POIs, road labels and shields, airports, paths). Dropping them makes the
 * first render much cheaper on phones and keeps the map calm.
 */
import type { StyleSpecification } from 'maplibre-gl';

const DROP =
	/building|aeroway|airport|pier|path|minor|oneway|tunnel|bridge|transit|service|shield|highway[-_]name|road_|poi|housenumber|park|residential/;

export function slimBasemap(style: StyleSpecification): StyleSpecification {
	return {
		...style,
		layers: style.layers.filter((l) => l.type === 'background' || !DROP.test(l.id))
	};
}

/** Where the climate layer goes: above roads and land cover, under boundaries and labels. */
export function climateLayerBefore(layers: StyleSpecification['layers']): string | undefined {
	return (
		layers.find((l) => l.id.startsWith('boundary'))?.id ??
		layers.find((l) => l.type === 'symbol')?.id
	);
}

/** Copies the climate source and layer from `prev` into `next`, so switching style keeps them. */
export function withClimateLayer(
	prev: StyleSpecification | undefined,
	next: StyleSpecification,
	id: string
): StyleSpecification {
	const source = prev?.sources?.[id];
	const layer = prev?.layers?.find((l) => l.id === id);
	if (!source || !layer) return next;
	const layers = next.layers.filter((l) => l.id !== id);
	const before = climateLayerBefore(layers);
	const at = before ? layers.findIndex((l) => l.id === before) : layers.length;
	layers.splice(at, 0, layer);
	return { ...next, sources: { ...next.sources, [id]: source }, layers };
}
