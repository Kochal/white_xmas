import { describe, expect, it } from 'vitest';
import { LruCache } from './cache';

describe('LruCache', () => {
	it('evicts the least recently used entry beyond its capacity', () => {
		const c = new LruCache<string, number>(2);
		c.set('a', 1);
		c.set('b', 2);
		c.get('a'); // a is now most recent
		c.set('c', 3);
		expect(c.has('a')).toBe(true);
		expect(c.has('b')).toBe(false);
		expect(c.has('c')).toBe(true);
		expect(c.size).toBe(2);
	});

	it('loads each key once, sharing the in-flight promise', async () => {
		const c = new LruCache<string, Promise<number>>(4);
		let calls = 0;
		const load = async () => {
			calls++;
			return 42;
		};
		const [x, y] = await Promise.all([c.getOrLoad('k', load), c.getOrLoad('k', load)]);
		expect([x, y]).toEqual([42, 42]);
		expect(calls).toBe(1);
	});

	it('forgets a failed load so it can be retried', async () => {
		const c = new LruCache<string, Promise<number>>(4);
		await expect(c.getOrLoad('k', () => Promise.reject(new Error('offline')))).rejects.toThrow(
			'offline'
		);
		expect(c.has('k')).toBe(false);
		expect(await c.getOrLoad('k', async () => 7)).toBe(7);
	});
});
