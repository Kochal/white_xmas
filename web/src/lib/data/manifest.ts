/**
 * Typed loader for `manifest.json` (web data contract v1, § manifest.json).
 * The site only shows what the manifest lists; anything else is never assumed.
 */

import { parseAdmin1Ref, type Admin1Ref } from './admin1';

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
	/** Threshold id (contract v1.5); filled with the default threshold's id when absent. */
	threshold: string;
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
/** Contract v1.2: median projected probability minus the baseline window's, in pp. */
export interface ProjectionChangeLayer extends LayerBase {
	kind: 'projection_change';
	warming_level: number;
	/** Cells where fewer than 2 in 3 models agree on the direction of change are hatched. */
	hatch_disagreement?: boolean;
}

export type Layer =
	ProbabilityLayer | ChangeLayer | TrendLayer | ProjectionLayer | ProjectionChangeLayer;
export type LayerKind = Layer['kind'];
const LAYER_KINDS: readonly LayerKind[] = [
	'probability',
	'change',
	'trend',
	'projection',
	'projection_change'
];

/** Contract v1.5: a snow-depth threshold the site can show (e.g. calibrated 5 cm, raw 1 cm). */
export interface Threshold {
	id: string;
	/** whole centimetres of daily-mean snow depth in ERA5-Land */
	cm: number;
	default?: boolean;
	/** set when `cm` is calibrated to match this depth at weather stations */
	station_equivalent_cm?: number;
	label: string;
	description: string;
}

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
	/** The default threshold in cm (kept for v1.4 readers; see `thresholds`). */
	threshold_cm: number;
	/** Thresholds the data offers; one entry built from threshold_cm when the manifest has none. */
	thresholds: Threshold[];
	/**
	 * Optional: the station snow depth the threshold corresponds to, when the threshold is
	 * calibrated (e.g. 4 cm in ERA5-Land ≈ 1 cm at a weather station).
	 */
	station_equivalent_cm?: number;
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
	/** Contract v1.6: states and provinces; undefined when the data doesn't list them. */
	admin1?: Admin1Ref;
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
	const thresholdCm = typeof raw.threshold_cm === 'number' ? raw.threshold_cm : 1;
	const stationCm =
		typeof raw.station_equivalent_cm === 'number' ? raw.station_equivalent_cm : undefined;
	const thresholds = parseThresholds(raw.thresholds, thresholdCm, stationCm);
	const defaultId = (thresholds.find((t) => t.default) ?? thresholds[0]).id;
	for (const l of layers) if (typeof l.threshold !== 'string') l.threshold = defaultId;
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
		threshold_cm: thresholdCm,
		thresholds,
		attribution: typeof raw.attribution === 'string' ? raw.attribution : '',
		definitions,
		windows,
		layers,
		colormaps: isObject(raw.colormaps) ? (raw.colormaps as Record<string, Colormap>) : {},
		projections,
		places: typeof raw.places === 'string' ? raw.places : 'places.json',
		regions: typeof raw.regions === 'string' ? raw.regions : 'regions.json',
		admin1: parseAdmin1Ref(raw.admin1)
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

function parseThresholds(raw: unknown, thresholdCm: number, stationCm?: number): Threshold[] {
	const list = Array.isArray(raw)
		? (raw as Partial<Threshold>[]).filter(
				(t): t is Threshold => isObject(t) && typeof t.id === 'string' && typeof t.cm === 'number'
			)
		: [];
	if (list.length) {
		const out = list.map((t) => ({
			...t,
			label: t.label ?? `${t.cm} cm`,
			description: t.description ?? ''
		}));
		if (!out.some((t) => t.default)) out[0] = { ...out[0], default: true };
		return out;
	}
	// v1.4 and earlier: a single threshold
	return [
		{
			id: 'default',
			cm: thresholdCm,
			default: true,
			station_equivalent_cm: stationCm,
			label: stationCm !== undefined ? 'Calibrated to weather stations' : `${thresholdCm} cm`,
			description: ''
		}
	];
}

export function defaultThreshold(m: Manifest): Threshold {
	return m.thresholds.find((t) => t.default) ?? m.thresholds[0];
}

export function thresholdById(m: Manifest, id: string | undefined): Threshold {
	return m.thresholds.find((t) => t.id === id) ?? defaultThreshold(m);
}

/** Short label for the switch: "Calibrated to stations" or "Raw ERA5-Land (1 cm)". */
export function thresholdShortLabel(t: Threshold): string {
	return t.station_equivalent_cm !== undefined
		? 'Calibrated to stations'
		: `Raw ERA5-Land (${t.cm} cm)`;
}

/** "Calibrated: 5 cm in ERA5-Land ≈ 1 cm at a weather station.", or null without calibration. */
export function thresholdNote(m: Manifest, t: Threshold = defaultThreshold(m)): string | null {
	const s = t.station_equivalent_cm;
	if (typeof s !== 'number' || !Number.isFinite(s)) return null;
	return `Calibrated: ${t.cm} cm in ERA5-Land ≈ ${s} cm at a weather station.`;
}

/**
 * A definition's description for a threshold: the manifest writes it for the default
 * threshold ("… at least 5 cm."), so the number is rewritten for another one.
 */
export function definitionText(m: Manifest, d: Definition, t: Threshold): string {
	const def = defaultThreshold(m);
	if (t.cm === def.cm) return d.description;
	return d.description.replace(new RegExp(`\\b${def.cm}(\\s?)cm\\b`, 'g'), `${t.cm}$1cm`);
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
