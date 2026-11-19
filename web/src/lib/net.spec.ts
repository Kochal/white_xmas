import { describe, expect, it } from 'vitest';
import { allowsPrefetch } from './net';

describe('allowsPrefetch', () => {
	it('respects Save-Data and slow connections, and allows unknown ones', () => {
		expect(allowsPrefetch(undefined)).toBe(true);
		expect(allowsPrefetch({ effectiveType: '4g' })).toBe(true);
		expect(allowsPrefetch({ effectiveType: '3g' })).toBe(true);
		expect(allowsPrefetch({ saveData: true, effectiveType: '4g' })).toBe(false);
		expect(allowsPrefetch({ effectiveType: '2g' })).toBe(false);
		expect(allowsPrefetch({ effectiveType: 'slow-2g' })).toBe(false);
	});
});
