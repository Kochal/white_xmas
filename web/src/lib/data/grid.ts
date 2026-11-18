/**
 * The ERA5-Land 0.1° global grid and the 5° point tiling, as defined in the web
 * data contract (§ Grid, § Point tiles). Cell centres sit at
 * lon = −180 + 0.1·i (i = 0…3599) and lat = 90 − 0.1·j (j = 0…1800).
 */

export const GRID_RES = 0.1;
export const N_LON = 3600;
export const N_LAT = 1801;
export const TILE_CELLS = 50;

export interface Cell {
	i: number;
	j: number;
}

export interface TileAddress {
	tx: number;
	ty: number;
	/** Column of the cell inside the tile (0…49, west → east). */
	ci: number;
	/** Row of the cell inside the tile (0…49, north → south). */
	cj: number;
	/** `${tx}_${ty}`, as used in `points/index.json` and file names. */
	key: string;
}

/** The grid cell whose centre is nearest to a coordinate. */
export function cellOf(lon: number, lat: number): Cell {
	const i = (((Math.round((lon + 180) / GRID_RES) % N_LON) + N_LON) % N_LON) | 0;
	const clampedLat = Math.max(-90, Math.min(90, lat));
	const j = Math.round((90 - clampedLat) / GRID_RES);
	return { i, j };
}

export function cellCentre(cell: Cell): { lon: number; lat: number } {
	return { lon: -180 + GRID_RES * cell.i, lat: 90 - GRID_RES * cell.j };
}

export function tileOf(cell: Cell): TileAddress {
	const tx = Math.floor(cell.i / TILE_CELLS);
	const ty = Math.floor(cell.j / TILE_CELLS);
	return { tx, ty, ci: cell.i - TILE_CELLS * tx, cj: cell.j - TILE_CELLS * ty, key: `${tx}_${ty}` };
}
