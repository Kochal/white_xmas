/** Rankings of states and provinces, computed from the admin1 index (default threshold). */
import type { RegionRow } from '#lib/data/admin1.ts';

export type RegionMetric = 'snowiest' | 'least_snowy' | 'decline';

export const METRIC_LABELS: Record<RegionMetric, string> = {
	snowiest: 'Snowiest',
	least_snowy: 'Least snowy',
	decline: 'Biggest decline'
};

export interface RegionFilter {
	/** Country key (`DEU`); undefined for the whole world. */
	country?: string;
	/** Include low-resolution regions (fewer than 3 land cells); off for the world list. */
	includeSmall?: boolean;
}

export const isSmall = (r: RegionRow) => r.flags.includes('low_res');

/** A decline only counts for regions that had a white Christmas at least 1 year in 10 before. */
export const DECLINE_MIN_THEN = 10;

/** Antarctica's two rows are ice sheet, not a state or province anyone ranks. */
const WORLD_EXCLUDED = new Set(['ATA']);

/** Regions of the scope a ranking draws from (country, small ones, Antarctica). */
function scope(rows: RegionRow[], filter: RegionFilter): RegionRow[] {
	// within one country every region is listed (small ones are marked); worldwide they are left out
	const small = filter.includeSmall ?? !!filter.country;
	return rows.filter((r) =>
		filter.country
			? r.country === filter.country && (small || !isSmall(r))
			: !WORLD_EXCLUDED.has(r.country) && (small || !isSmall(r))
	);
}

const byName = (a: RegionRow, b: RegionRow) => a.name.localeCompare(b.name, 'en');
/** null sorts as 0 (it has no value); ties then fall through to the next key. */
const v = (x: number | null) => x ?? 0;

/**
 * Many regions share 100 % or 0 % (every year white, or never), so ties are ordered by the
 * longer record (1950–2025) and then the earlier normal, not alphabetically.
 */
const snowierFirst = (a: RegionRow, b: RegionRow) =>
	v(b.p_now) - v(a.p_now) || v(b.p_full) - v(a.p_full) || v(b.p_then) - v(a.p_then) || byName(a, b);
const lessSnowyFirst = (a: RegionRow, b: RegionRow) =>
	v(a.p_now) - v(b.p_now) || v(a.p_full) - v(b.p_full) || v(a.p_then) - v(b.p_then) || byName(a, b);

/** Whether a region ever had snow at Christmas in the record (p_full above 0). */
const everSnowed = (r: RegionRow) => (r.p_full !== null ? r.p_full > 0 : (r.p_now ?? 0) > 0);

function candidates(rows: RegionRow[], metric: RegionMetric, filter: RegionFilter): RegionRow[] {
	const pool = scope(rows, filter);
	switch (metric) {
		case 'snowiest':
			return pool.filter((r) => r.p_now !== null).sort(snowierFirst);
		case 'least_snowy':
			// regions with no values have no data; regions that never had snow are counted apart
			return pool.filter((r) => r.p_now !== null && everSnowed(r)).sort(lessSnowyFirst);
		case 'decline':
			return pool
				.filter(
					(r) =>
						r.change !== null && r.change < 0 && r.p_then !== null && r.p_then >= DECLINE_MIN_THEN
				)
				.sort((a, b) => a.change! - b.change! || v(b.p_then) - v(a.p_then) || byName(a, b));
	}
}

export function rankRegions(
	rows: RegionRow[],
	metric: RegionMetric,
	filter: RegionFilter,
	limit: number
): RegionRow[] {
	return candidates(rows, metric, filter).slice(0, limit);
}

export interface RankSummary {
	/** Regions in the ranking before the limit. */
	total: number;
	/** The first region's value in whole %, and how many regions in the ranking share it. */
	top: { value: number; count: number } | null;
	/** Least snowy only: regions with values that never had snow (0 %), left out of the list. */
	never: number;
}

/**
 * What the list hides: how many regions share the top value (100 % or 0 % for most of the
 * world), so the page can say "N regions at 100 %" instead of implying the 25 shown are special.
 */
export function rankSummary(
	rows: RegionRow[],
	metric: RegionMetric,
	filter: RegionFilter
): RankSummary {
	const list = candidates(rows, metric, filter);
	let top: RankSummary['top'] = null;
	if (list.length && metric !== 'decline') {
		const value = Math.round(list[0].p_now!);
		top = { value, count: list.filter((r) => Math.round(r.p_now!) === value).length };
	}
	const never =
		metric === 'least_snowy'
			? scope(rows, filter).filter((r) => r.p_now !== null && !everSnowed(r)).length
			: 0;
	return { total: list.length, top, never };
}

/** Countries that have regions in the index, A–Z by name. */
export function countryOptions(
	countries: Record<string, { name: string; regions: number }>
): { code: string; name: string; regions: number }[] {
	return Object.entries(countries)
		.map(([code, c]) => ({ code, name: c.name, regions: c.regions }))
		.sort((a, b) => a.name.localeCompare(b.name, 'en', { sensitivity: 'base' }));
}
