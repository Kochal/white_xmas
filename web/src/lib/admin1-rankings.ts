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

export function rankRegions(
	rows: RegionRow[],
	metric: RegionMetric,
	filter: RegionFilter,
	limit: number
): RegionRow[] {
	// within one country every region is listed (small ones are marked); worldwide they are left out
	const small = filter.includeSmall ?? !!filter.country;
	const pool = rows.filter(
		(r) => (!filter.country || r.country === filter.country) && (small || !isSmall(r))
	);
	const byName = (a: RegionRow, b: RegionRow) => a.name.localeCompare(b.name, 'en');
	switch (metric) {
		case 'snowiest':
			return pool
				.filter((r) => r.p_now !== null)
				.sort((a, b) => b.p_now! - a.p_now! || byName(a, b))
				.slice(0, limit);
		case 'least_snowy':
			// regions with no values at all are not "least snowy": they have no data
			return pool
				.filter((r) => r.p_now !== null)
				.sort((a, b) => a.p_now! - b.p_now! || byName(a, b))
				.slice(0, limit);
		case 'decline':
			return pool
				.filter(
					(r) =>
						r.change !== null && r.change < 0 && r.p_then !== null && r.p_then >= DECLINE_MIN_THEN
				)
				.sort((a, b) => a.change! - b.change! || byName(a, b))
				.slice(0, limit);
	}
}

/** Countries that have regions in the index, A–Z by name. */
export function countryOptions(
	countries: Record<string, { name: string; regions: number }>
): { code: string; name: string; regions: number }[] {
	return Object.entries(countries)
		.map(([code, c]) => ({ code, name: c.name, regions: c.regions }))
		.sort((a, b) => a.name.localeCompare(b.name, 'en', { sensitivity: 'base' }));
}
