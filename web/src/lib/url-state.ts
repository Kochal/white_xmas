/**
 * Shareable URL state in the query string:
 * `?def=<definition>&layer=<kind>&period=<period>&map=<zoom>/<lat>/<lon>&at=<lat>,<lon>&place=<name>`
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
}

const KINDS: LayerKind[] = ['probability', 'change', 'trend', 'projection'];

const finite = (s: string | undefined) => {
	const n = Number(s);
	return s !== undefined && s.trim() !== '' && Number.isFinite(n) ? n : null;
};

export function parseUrlState(params: URLSearchParams): UrlState {
	const state: UrlState = { selection: {} };
	const def = params.get('def');
	if (def) state.selection.definition = def;
	const kind = params.get('layer') as LayerKind | null;
	if (kind && KINDS.includes(kind)) state.selection.kind = kind;
	const period = params.get('period');
	if (period) state.selection.period = period;

	const [z, la, lo] = (params.get('map') ?? '').split('/').map(finite);
	if (z !== null && la !== null && lo !== null && z >= 0 && z <= 22 && Math.abs(la) <= 85.06)
		state.view = { zoom: z, lat: la, lon: lo };

	const [alat, alon] = (params.get('at') ?? '').split(',').map(finite);
	if (alat !== null && alon !== null && Math.abs(alat) <= 90 && Math.abs(alon) <= 360)
		state.at = { lat: alat, lon: alon };

	const place = params.get('place');
	if (place && state.at) state.place = place.slice(0, 120);
	return state;
}

export function serializeUrlState(state: UrlState): string {
	const p = new URLSearchParams();
	const s = state.selection;
	if (s.definition) p.set('def', s.definition);
	if (s.kind) p.set('layer', s.kind);
	if (s.period) p.set('period', s.period);
	if (state.view)
		p.set(
			'map',
			`${Number(state.view.zoom.toFixed(2))}/${state.view.lat.toFixed(4)}/${state.view.lon.toFixed(4)}`
		);
	if (state.at) p.set('at', `${state.at.lat.toFixed(4)},${state.at.lon.toFixed(4)}`);
	if (state.at && state.place) p.set('place', state.place);
	const qs = p.toString();
	return qs ? `?${qs}` : '';
}
