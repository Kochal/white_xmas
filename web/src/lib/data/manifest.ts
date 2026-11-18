/**
 * Typed loader for `manifest.json` (web data contract v1, § manifest.json).
 * The site only shows what the manifest lists; anything else is never assumed.
 */

export const SCHEMA_VERSION = 1;

export type DefinitionId = 'christmas_day' | 'all_three_days' | 'any_day' | (string & {});

export interface Definition {
	id: DefinitionId;
	label: string;
	short: string;
	description: string;
	default?: boolean;
}

export type WindowKind = 'full' | 'normal' | 'decade';

export interface Window {
	id: string;
	label: string;
	start: number;
	end: number;
	kind: WindowKind;
}

interface LayerBase {
	id: string;
	definition: DefinitionId;
	url: string;
	colormap: string;
	minzoom?: number;
	maxzoom?: number;
}

export interface ProbabilityLayer extends LayerBase {
	kind: 'probability';
	window: string;
}
export interface ChangeLayer extends LayerBase {
	kind: 'change';
	from: string;
	to: string;
}
export interface TrendLayer extends LayerBase {
	kind: 'trend';
	window: string;
	hatch_insignificant?: boolean;
}
export interface ProjectionLayer extends LayerBase {
	kind: 'projection';
	warming_level: number;
}

export type Layer = ProbabilityLayer | ChangeLayer | TrendLayer | ProjectionLayer;
export type LayerKind = Layer['kind'];
const LAYER_KINDS: readonly LayerKind[] = ['probability', 'change', 'trend', 'projection'];

export interface Colormap {
	unit: string;
	domain: [number, number];
	stops: [number, string][];
}

export interface WarmingLevel {
	gwl: number;
	label: string;
	approx: string;
}

export interface Projections {
	available: boolean;
	warming_levels: WarmingLevel[];
	baseline_window?: string;
	points?: { tile_deg: number; format: string; path: string };
	models: string[];
}

export interface Manifest {
	schema_version: 1;
	data_version: string;
	built: string;
	build_hash: string;
	years: { first: number; last: number };
	threshold_cm: number;
	attribution: string;
	definitions: Definition[];
	windows: Window[];
	layers: Layer[];
	colormaps: Record<string, Colormap>;
	glacier_style?: string;
	points: { index: string; tile_deg: number; format: string };
	projections: Projections;
	places: string;
	regions: string;
}

export class ManifestError extends Error {
	constructor(message: string) {
		super(`manifest.json: ${message}`);
		this.name = 'ManifestError';
	}
}

const isObject = (v: unknown): v is Record<string, unknown> =>
	typeof v === 'object' && v !== null && !Array.isArray(v);

function nonEmptyArray(raw: Record<string, unknown>, key: string): unknown[] {
	const v = raw[key];
	if (!Array.isArray(v) || v.length === 0)
		throw new ManifestError(`"${key}" must be a non-empty list`);
	return v;
}

/** Validates the parts of the manifest the site relies on and fills optional defaults. */
export function parseManifest(raw: unknown): Manifest {
	if (!isObject(raw)) throw new ManifestError('not a JSON object');
	if (raw.schema_version !== SCHEMA_VERSION)
		throw new ManifestError(
			`schema_version ${String(raw.schema_version)} is not supported (this site reads ${SCHEMA_VERSION})`
		);
	const years = raw.years;
	if (!isObject(years) || typeof years.first !== 'number' || typeof years.last !== 'number')
		throw new ManifestError('"years" must be { first, last }');

	const definitions = nonEmptyArray(raw, 'definitions') as Definition[];
	const windows = nonEmptyArray(raw, 'windows') as Window[];
	if (!Array.isArray(raw.layers)) throw new ManifestError('"layers" must be a list');
	const layers = (raw.layers as Layer[]).filter(
		(l) => isObject(l) && LAYER_KINDS.includes(l.kind) && typeof l.url === 'string'
	);
	const points = raw.points;
	if (!isObject(points) || typeof points.index !== 'string')
		throw new ManifestError('"points.index" is missing');

	const proj = isObject(raw.projections) ? raw.projections : {};
	const projections: Projections = {
		...(proj as Partial<Projections>),
		available: proj.available === true,
		warming_levels: Array.isArray(proj.warming_levels)
			? (proj.warming_levels as WarmingLevel[])
			: [],
		models: Array.isArray(proj.models) ? (proj.models as string[]) : []
	};

	return {
		...(raw as unknown as Manifest),
		threshold_cm: typeof raw.threshold_cm === 'number' ? raw.threshold_cm : 1,
		attribution: typeof raw.attribution === 'string' ? raw.attribution : '',
		definitions,
		windows,
		layers,
		colormaps: isObject(raw.colormaps) ? (raw.colormaps as Record<string, Colormap>) : {},
		projections,
		places: typeof raw.places === 'string' ? raw.places : 'places.json',
		regions: typeof raw.regions === 'string' ? raw.regions : 'regions.json'
	};
}

export async function loadManifest(
	dataBase: string,
	fetchFn: typeof fetch = fetch
): Promise<Manifest> {
	const url = `${dataBase}/manifest.json`;
	const res = await fetchFn(url);
	if (!res.ok) throw new ManifestError(`could not load ${url} (HTTP ${res.status})`);
	return parseManifest(await res.json());
}

export function defaultDefinition(m: Manifest): Definition {
	return m.definitions.find((d) => d.default) ?? m.definitions[0];
}

export interface LayerQuery {
	kind: LayerKind;
	definition: DefinitionId;
	window?: string;
	from?: string;
	to?: string;
	warming_level?: number;
}

/** The first layer matching every given field of the query. */
export function findLayer(m: Manifest, q: LayerQuery): Layer | undefined {
	return m.layers.find(
		(l) =>
			l.kind === q.kind &&
			l.definition === q.definition &&
			(q.window === undefined || ('window' in l && l.window === q.window)) &&
			(q.from === undefined || ('from' in l && l.from === q.from)) &&
			(q.to === undefined || ('to' in l && l.to === q.to)) &&
			(q.warming_level === undefined ||
				('warming_level' in l && Math.abs(l.warming_level - q.warming_level) < 1e-9))
	);
}

export function windowById(m: Manifest, id: string): Window | undefined {
	return m.windows.find((w) => w.id === id);
}
