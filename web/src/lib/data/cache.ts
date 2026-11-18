/** A small least-recently-used cache. Map iteration order is insertion order. */
export class LruCache<K, V> {
	#map = new Map<K, V>();

	constructor(readonly capacity: number) {}

	get size(): number {
		return this.#map.size;
	}

	has(key: K): boolean {
		return this.#map.has(key);
	}

	get(key: K): V | undefined {
		if (!this.#map.has(key)) return undefined;
		const value = this.#map.get(key)!;
		this.#map.delete(key);
		this.#map.set(key, value);
		return value;
	}

	set(key: K, value: V): void {
		this.#map.delete(key);
		this.#map.set(key, value);
		while (this.#map.size > this.capacity) {
			this.#map.delete(this.#map.keys().next().value as K);
		}
	}

	delete(key: K): void {
		this.#map.delete(key);
	}

	/**
	 * For promise-valued caches: returns the cached promise or starts `load`, caching the
	 * promise itself so concurrent callers share one request. Failed loads are evicted.
	 */
	getOrLoad<T>(this: LruCache<K, Promise<T>>, key: K, load: () => Promise<T>): Promise<T> {
		const hit = this.get(key);
		if (hit) return hit;
		const p = load();
		this.set(key, p);
		p.catch(() => {
			if (this.#map.get(key) === p) this.#map.delete(key);
		});
		return p;
	}
}
