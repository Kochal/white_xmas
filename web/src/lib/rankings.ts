/** Rankings computed from places.json (contract § places.json). */
import type { Place } from '#lib/data/places.ts';

/** Places with at least `minPop` people, highest recent probability first. */
export function snowiest(places: Place[], minPop: number, limit: number): Place[] {
	return places
		.filter((p) => p.pop >= minPop && p.p_now !== null)
		.sort((a, b) => b.p_now! - a.p_now! || b.pop - a.pop)
		.slice(0, limit);
}

/**
 * Largest declines from the "then" to the "now" normal, in percentage points. Only places
 * that had a white Christmas at least 1 in 10 years before are ranked, so that tiny
 * probabilities don't fill the list with noise.
 */
export function declines(places: Place[], minPop: number, limit: number): Place[] {
	return places
		.filter((p) => p.pop >= minPop && p.p_then !== null && p.p_now !== null && p.p_then >= 10)
		.filter((p) => p.p_now! < p.p_then!)
		.sort((a, b) => a.p_now! - a.p_then! - (b.p_now! - b.p_then!) || b.pop - a.pop)
		.slice(0, limit);
}
