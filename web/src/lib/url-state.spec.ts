import { describe, expect, it } from 'vitest';
import { parseUrlState, serializeUrlState } from './url-state';

describe('URL state', () => {
	it('round-trips view, selection and the selected place', () => {
		const state = {
			view: { zoom: 5.25, lat: 48.1, lon: 11.5 },
			selection: {
				definition: 'christmas_day',
				threshold: 'raw',
				kind: 'change' as const,
				period: '1961_1990__1996_2025'
			},
			at: { lat: 48.14, lon: 11.58 },
			place: 'Munich'
		};
		const qs = serializeUrlState(state);
		expect(qs).toBe(
			'?def=christmas_day&th=raw&layer=change&period=1961_1990__1996_2025&map=5.25%2F48.1000%2F11.5000&at=48.1400%2C11.5800&place=Munich'
		);
		expect(parseUrlState(new URLSearchParams(qs))).toEqual(state);
	});

	it('ignores malformed values instead of failing', () => {
		const s = parseUrlState(new URLSearchParams('map=abc&at=95,10&layer=bogus&def=x'));
		expect(s.view).toBeUndefined();
		expect(s.at).toBeUndefined();
		expect(s.selection.kind).toBeUndefined();
		expect(s.selection.definition).toBe('x'); // validated later against the manifest
	});

	it('leaves out what is not set', () => {
		expect(serializeUrlState({ selection: {} })).toBe('');
	});
});
