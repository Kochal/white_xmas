/**
 * Shareable URL state in the query string:
 * `?def=<definition>&th=<threshold>&layer=<kind>&period=<period>&map=<zoom>/<lat>/<lon>&at=<lat>,<lon>&place=<name>`
 * plus, for states and provinces (contract v1.6), `&regions=1` (borders layer on) and the
 * deep link `#/region/<id>` (for example `#/region/DE-BY`) for a selected region.
 */
import type { LayerKind } from '#lib/data/manifest.ts';
import type { Selection } from '#lib/map/layers.ts';

export interface MapView {
	zoom: number;
	lat: number;
	lon: number;
}

export interface UrlState {
	view?: MapView;
	selection: Partial<Selection>;
	at?: { lat: number; lon: number };
	place?: string;
	/** State/province borders layer on. */
	regions?: boolean;
	/** Selected region id, from the URL hash. */
	region?: string;
	/** A `#/region/<x>` link whose id is not a valid id: kept (shortened) to say so. */
	regionRejected?: string;
}

/**
 * Region ids are ISO 3166-2 codes or Natural Earth fallbacks: letters, digits and `-`. The
 * longest real one (`SVN-JUGOVZHODNA-SLOVENIJA`) has 25 characters; the limit leaves room.
 */
export const REGION_ID = /^[A-Za-z0-9][A-Za-z0-9-]{0,47}$/;

const KINDS: LayerKind[] = ['probability', 'change', 'trend', 'projection', 'projection_change'];

const finite = (s: string | undefined) => {
	const n = Number(s);
	return s !== undefined && s.trim() !== '' && Number.isFinite(n) ? n : null;
};

/** `#/region/DE-BY` -> `DE-BY`; anything else -> undefined. */
export function parseRegionHash(hash: string): string | undefined {
	const m = /^#\/region\/([^/?#]+)\/?$/.exec(hash);
	if (!m) return undefined;
	let id: string;
	try {
		id = decodeURIComponent(m[1]);
	} catch {
		return undefined;
	}
	return REGION_ID.test(id) ? id : undefined;
}

/** The text of a `#/region/<x>` hash that parseRegionHash refused, shortened for display. */
export function rejectedRegionHash(hash: string): string | undefined {
	const m = /^#\/region\/(.+)$/.exec(hash);
	if (!m || parseRegionHash(hash)) return undefined;
	let raw = m[1];
	try {
		raw = decodeURIComponent(raw);
	} catch {
		/* keep the raw text */
	}
	return raw.replace(/[^\p{L}\p{N} _./-]/gu, '').slice(0, 60) || undefined;
}

export const regionHash = (id: string | undefined): string =>
	id && REGION_ID.test(id) ? `#/region/${encodeURIComponent(id)}` : '';

export function parseUrlState(params: URLSearchParams, hash = ''): UrlState {
	const state: UrlState = { selection: {} };
	const def = params.get('def');
	if (def) state.selection.definition = def;
	const kind = params.get('layer') as LayerKind | null;
	if (kind && KINDS.includes(kind)) state.selection.kind = kind;
	const period = params.get('period');
	if (period) state.selection.period = period;
	const th = params.get('th');
	if (th) state.selection.threshold = th;

	const [z, la, lo] = (params.get('map') ?? '').split('/').map(finite);
	if (z !== null && la !== null && lo !== null && z >= 0 && z <= 22 && Math.abs(la) <= 85.06)
		state.view = { zoom: z, lat: la, lon: lo };

	const [alat, alon] = (params.get('at') ?? '').split(',').map(finite);
	if (alat !== null && alon !== null && Math.abs(alat) <= 90 && Math.abs(alon) <= 360)
		state.at = { lat: alat, lon: alon };

	const place = params.get('place');
	if (place && state.at) state.place = place.slice(0, 120);

	if (params.get('regions') === '1') state.regions = true;
	const region = parseRegionHash(hash);
	if (region) {
		// a region and a point are never selected together; the region link wins. The borders
		// layer stays as the link says (?regions=1): a region draws only its own outline.
		state.region = region;
		delete state.at;
		delete state.place;
	} else {
		const rejected = rejectedRegionHash(hash);
		if (rejected) state.regionRejected = rejected;
	}
	return state;
}

export function serializeUrlState(state: UrlState): string {
	const p = new URLSearchParams();
	const s = state.selection;
	if (s.definition) p.set('def', s.definition);
	if (s.threshold) p.set('th', s.threshold);
	if (s.kind) p.set('layer', s.kind);
	if (s.period) p.set('period', s.period);
	if (state.view)
		p.set(
			'map',
			`${Number(state.view.zoom.toFixed(2))}/${state.view.lat.toFixed(4)}/${state.view.lon.toFixed(4)}`
		);
	if (state.at) p.set('at', `${state.at.lat.toFixed(4)},${state.at.lon.toFixed(4)}`);
	if (state.at && state.place) p.set('place', state.place);
	if (state.regions) p.set('regions', '1');
	const qs = p.toString();
	return qs ? `?${qs}` : '';
}

/** What goes after the path: the query string plus the region hash. */
export const serializeUrl = (state: UrlState): string =>
	serializeUrlState(state) + regionHash(state.region);
