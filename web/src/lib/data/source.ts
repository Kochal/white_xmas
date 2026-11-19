/**
 * One entry point for all data the site reads, with caching: the manifest, the point
 * index and tiles, projection tiles, places and regions.
 */
import {
	loadAdmin1Index,
	loadBoundaries,
	loadCountry,
	type Admin1Index,
	type BoundaryCollection,
	type CountryFile
} from './admin1';
import { LruCache } from './cache';
import { cellCentre, cellOf, tileOf, type Cell, type TileAddress } from './grid';
import { loadManifest, type Manifest } from './manifest';
import { fetchPlacesFile, type Place, type PlacesMeta } from './places';
import {
	cellHistory,
	cellProjection,
	fetchPointIndex,
	fetchPointTile,
	fetchProjTile,
	type CellHistory,
	type PointTile,
	type ProjTile,
	type ProjectedProbability
} from './points';
import { loadRegions, type Region } from './regions';

export type LookupStatus = 'ok' | 'ocean' | 'outside';

export interface CellLookup {
	/** The cell the data comes from (may be a nearby land cell for a coastal place). */
	cell: Cell;
	centre: { lon: number; lat: number };
	tile: TileAddress;
	/** 'outside': no point tile covers it; 'ocean': all nodata. */
	status: LookupStatus;
	history: CellHistory | null;
	/** Per warming level (manifest order), when projections are available. */
	projection: ProjectedProbability[] | null;
	/** True when a neighbouring land cell was used instead of the requested one. */
	moved: boolean;
}

export class DataSource {
	#tiles = new LruCache<string, Promise<PointTile>>(32);
	#proj = new LruCache<string, Promise<ProjTile>>(32);
	#index: Promise<Set<string>> | null = null;
	#places: Promise<{ places: Place[]; meta: PlacesMeta }> | null = null;
	#regions: Promise<Region[]> | null = null;
	#admin1Index: Promise<Admin1Index> | null = null;
	#admin1Boundaries: Promise<BoundaryCollection> | null = null;
	#admin1Countries = new LruCache<string, Promise<CountryFile>>(8);

	constructor(
		readonly base: string,
		readonly manifest: Manifest,
		private readonly fetchFn: typeof fetch = (...args) => fetch(...args)
	) {}

	static async open(base: string, fetchFn?: typeof fetch): Promise<DataSource> {
		const f = fetchFn ?? ((...args: Parameters<typeof fetch>) => fetch(...args));
		return new DataSource(base, await loadManifest(base, f), f);
	}

	/** Absolute or base-relative URL of a manifest-relative path. */
	url(path: string): string {
		return /^[a-z]+:\/\//i.test(path) ? path : `${this.base}/${path}`;
	}

	pointIndex(): Promise<Set<string>> {
		this.#index ??= fetchPointIndex(this.base, this.manifest.points.index, this.fetchFn).then(
			(i) => new Set(i.tiles)
		);
		this.#index.catch(() => (this.#index = null));
		return this.#index;
	}

	pointTile(key: string): Promise<PointTile> {
		return this.#tiles.getOrLoad(key, () => fetchPointTile(this.base, key, this.fetchFn));
	}

	projTile(tx: number, ty: number): Promise<ProjTile> | null {
		const p = this.manifest.projections;
		if (!p.available || !p.points?.path) return null;
		const path = p.points.path;
		return this.#proj.getOrLoad(`${tx}_${ty}`, () =>
			fetchProjTile(this.base, path, tx, ty, this.fetchFn)
		);
	}

	places(): Promise<{ places: Place[]; meta: PlacesMeta }> {
		this.#places ??= fetchPlacesFile(this.base, this.manifest.places, this.fetchFn);
		this.#places.catch(() => (this.#places = null));
		return this.#places;
	}

	regions(): Promise<Region[]> {
		this.#regions ??= loadRegions(this.base, this.manifest.regions, this.fetchFn);
		this.#regions.catch(() => (this.#regions = null));
		return this.#regions;
	}

	/** True when the manifest lists states and provinces (contract v1.6). */
	get hasAdmin1(): boolean {
		return !!this.manifest.admin1?.available;
	}

	/** States and provinces, one row per region (~130 kB gzipped); loaded on first use. */
	admin1Index(): Promise<Admin1Index> {
		const ref = this.manifest.admin1;
		if (!ref) return Promise.reject(new Error('states and provinces are not in this dataset'));
		this.#admin1Index ??= loadAdmin1Index(this.base, ref, this.fetchFn);
		this.#admin1Index.catch(() => (this.#admin1Index = null));
		return this.#admin1Index;
	}

	/** Outlines for the map layer (~1.4 MB gzipped); only fetched when the layer is switched on. */
	admin1Boundaries(): Promise<BoundaryCollection> {
		const ref = this.manifest.admin1;
		if (!ref) return Promise.reject(new Error('states and provinces are not in this dataset'));
		this.#admin1Boundaries ??= loadBoundaries(this.base, ref, this.fetchFn);
		this.#admin1Boundaries.catch(() => (this.#admin1Boundaries = null));
		return this.#admin1Boundaries;
	}

	/** All regions of one country with full statistics; fetched when a region of it opens. */
	admin1Country(country: string): Promise<CountryFile> {
		const ref = this.manifest.admin1;
		if (!ref) return Promise.reject(new Error('states and provinces are not in this dataset'));
		return this.#admin1Countries.getOrLoad(country, () =>
			loadCountry(this.base, ref, country, this.fetchFn)
		);
	}

	async #cellAt(cell: Cell): Promise<{ tile: TileAddress; history: CellHistory | null }> {
		const tile = tileOf(cell);
		const index = await this.pointIndex();
		if (!index.has(tile.key)) return { tile, history: null };
		const t = await this.pointTile(tile.key);
		return { tile, history: cellHistory(t, tile.ci, tile.cj) };
	}

	/**
	 * Looks up the cell containing a coordinate. With `nearestLand` > 0, an ocean or
	 * nodata cell falls back to the nearest land cell within that many cells, the same
	 * rule the pipeline uses for places.
	 */
	async lookup(lon: number, lat: number, opts: { nearestLand?: number } = {}): Promise<CellLookup> {
		const requested = cellOf(lon, lat);
		let cell = requested;
		let { tile, history } = await this.#cellAt(cell);
		let moved = false;
		const radius = opts.nearestLand ?? 0;
		if ((!history || history.ocean) && radius > 0) {
			const candidates: { cell: Cell; d: number }[] = [];
			for (let dj = -radius; dj <= radius; dj++)
				for (let di = -radius; di <= radius; di++) {
					if (di === 0 && dj === 0) continue;
					const j = requested.j + dj;
					if (j < 0 || j > 1800) continue;
					candidates.push({
						cell: { i: (requested.i + di + 3600) % 3600, j },
						d: di * di + dj * dj
					});
				}
			candidates.sort((a, b) => a.d - b.d);
			for (const c of candidates) {
				const r = await this.#cellAt(c.cell);
				if (r.history && !r.history.ocean) {
					({ tile, history } = r);
					cell = c.cell;
					moved = true;
					break;
				}
			}
		}
		const status: LookupStatus = !history ? 'outside' : history.ocean ? 'ocean' : 'ok';
		let projection: ProjectedProbability[] | null = null;
		if (status === 'ok') {
			const pt = this.projTile(tile.tx, tile.ty);
			if (pt) {
				try {
					projection = cellProjection(await pt, tile.ci, tile.cj);
				} catch {
					projection = null; // projections are optional; the panel just omits them
				}
			}
		}
		return {
			cell,
			centre: cellCentre(cell),
			tile,
			status,
			history: status === 'ok' ? history : null,
			projection,
			moved
		};
	}
}
