/**
 * Which map layer to show for the controls' selection (definition, kind, period), and
 * which options the controls offer. Only layers listed in the manifest are offered.
 * Future has two views (contract v1.2): projected probability and change vs today.
 */
import {
	defaultDefinition,
	type Layer,
	type LayerKind,
	type Manifest,
	type Window
} from '#lib/data/manifest.ts';

export interface Selection {
	definition: string;
	kind: LayerKind;
	/** window id (probability, trend), "<from>__<to>" (change) or a warming level (projection) */
	period: string;
}

export interface Option {
	value: string;
	label: string;
}

export const KIND_LABELS: Record<LayerKind, string> = {
	probability: 'Probability',
	change: 'Change',
	trend: 'Trend',
	projection: 'Future',
	projection_change: 'Future'
};

/** The two views under the Future tab (contract v1.2). */
export const FUTURE_MODE_LABELS = {
	projection: 'Probability',
	projection_change: 'Change vs today'
} as const;
export type FutureMode = keyof typeof FUTURE_MODE_LABELS;

const KIND_ORDER: LayerKind[] = ['probability', 'change', 'trend', 'projection'];

export const isFuture = (k: LayerKind): k is FutureMode =>
	k === 'projection' || k === 'projection_change';

/** Future views with at least one layer, when the manifest says projections are available. */
export function futureModes(m: Manifest, definition?: string): FutureMode[] {
	if (!m.projections.available) return [];
	return (['projection', 'projection_change'] as const).filter((k) =>
		m.layers.some((l) => l.kind === k && (definition === undefined || l.definition === definition))
	);
}

/**
 * The tabs the controls offer. `projection` stands for the Future tab, which also covers
 * `projection_change` layers. With a definition, Future is offered only when that definition
 * has projection layers (contract v1: Snow on Christmas Day only).
 */
export function availableKinds(m: Manifest, definition?: string): LayerKind[] {
	return KIND_ORDER.filter((k) =>
		k === 'projection' ? futureModes(m, definition).length > 0 : m.layers.some((l) => l.kind === k)
	);
}

const WINDOW_RANK: Record<string, number> = { full: 0, normal: 1, decade: 2 };

function windowSort(a: Window, b: Window): number {
	const r = (WINDOW_RANK[a.kind] ?? 3) - (WINDOW_RANK[b.kind] ?? 3);
	if (r !== 0) return r;
	return b.end - a.end || b.start - a.start;
}

function windowLabel(m: Manifest, id: string): string {
	return m.windows.find((w) => w.id === id)?.label ?? id.replace('_', '–');
}

function layerPeriod(l: Layer): string {
	switch (l.kind) {
		case 'probability':
		case 'trend':
			return l.window;
		case 'change':
			return `${l.from}__${l.to}`;
		case 'projection':
		case 'projection_change':
			return String(l.warming_level);
	}
}

export function periodOptions(m: Manifest, kind: LayerKind, definition: string): Option[] {
	const layers = m.layers.filter((l) => l.kind === kind && l.definition === definition);
	if (kind === 'probability' || kind === 'trend') {
		const ids = new Set(layers.map(layerPeriod));
		return m.windows
			.filter((w) => ids.has(w.id))
			.sort(windowSort)
			.map((w) => ({ value: w.id, label: w.label }));
	}
	if (kind === 'change') {
		return layers.map((l) => {
			const c = l as Extract<Layer, { kind: 'change' }>;
			return {
				value: layerPeriod(l),
				label: `${windowLabel(m, c.from)} → ${windowLabel(m, c.to)}`
			};
		});
	}
	// projection, projection_change: follow the manifest's warming-level order. The label
	// stays short; `approx` is derived and may be long (contract v1.3), so it's shown apart.
	const levels = new Set(layers.map((l) => Number(layerPeriod(l))));
	return m.projections.warming_levels
		.filter((w) => levels.has(w.gwl))
		.map((w) => ({ value: String(w.gwl), label: w.label }));
}

/** When a warming level is reached ("around the 2040s"), or '' if unknown. */
export function warmingLevelNote(m: Manifest, period: string): string {
	return m.projections.warming_levels.find((w) => String(w.gwl) === period)?.approx ?? '';
}

/** Fills in defaults and snaps invalid values to valid ones. */
export function normalizeSelection(m: Manifest, partial: Partial<Selection>): Selection {
	const definition = m.definitions.some((d) => d.id === partial.definition)
		? partial.definition!
		: defaultDefinition(m).id;
	const kinds = availableKinds(m);
	const modes = futureModes(m, definition);
	let kind: LayerKind;
	if (partial.kind && isFuture(partial.kind) && modes.length) {
		kind = modes.includes(partial.kind) ? partial.kind : modes[0];
	} else {
		kind =
			partial.kind && kinds.includes(partial.kind) && !isFuture(partial.kind)
				? partial.kind
				: (kinds[0] ?? 'probability');
	}
	const opts = periodOptions(m, kind, definition);
	let period = partial.period ?? '';
	if (!opts.some((o) => o.value === period)) {
		const preferred =
			kind === 'probability'
				? opts.find((o) => m.windows.find((w) => w.id === o.value)?.kind === 'normal')
				: undefined;
		period = (preferred ?? opts[0])?.value ?? '';
	}
	return { definition, kind, period };
}

export function resolveLayer(m: Manifest, sel: Selection): Layer | null {
	return (
		m.layers.find(
			(l) =>
				l.kind === sel.kind &&
				l.definition === sel.definition &&
				(sel.kind === 'projection'
					? Math.abs(Number(layerPeriod(l)) - Number(sel.period)) < 1e-9
					: layerPeriod(l) === sel.period)
		) ?? null
	);
}
