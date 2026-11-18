import { describe, expect, it } from 'vitest';
import { PMTiles, TileType as ReaderTileType } from 'pmtiles';
import { TileType, writePmtiles } from './pmtiles-writer.mjs';

class BufferSource {
	constructor(buf) {
		this.buf = buf;
	}
	getKey() {
		return 'mem';
	}
	async getBytes(offset, length) {
		const slice = this.buf.subarray(offset, offset + length);
		return { data: slice.buffer.slice(slice.byteOffset, slice.byteOffset + slice.byteLength) };
	}
}

describe('fixture PMTiles writer', () => {
	it('writes an archive the official reader can read back', async () => {
		const tiles = [
			{ z: 0, x: 0, y: 0, data: new Uint8Array([1, 2, 3]) },
			{ z: 2, x: 2, y: 1, data: new Uint8Array([4, 5]) },
			{ z: 1, x: 1, y: 0, data: new Uint8Array([6]) }
		];
		const buf = writePmtiles({ tiles, tileType: TileType.png, bounds: [-10, 40, 20, 60] });
		const archive = new PMTiles(new BufferSource(buf));
		const header = await archive.getHeader();
		expect(header.tileType).toBe(ReaderTileType.Png);
		expect(header.minZoom).toBe(0);
		expect(header.maxZoom).toBe(2);
		expect(header.minLon).toBeCloseTo(-10);
		expect(header.maxLat).toBeCloseTo(60);
		expect([...new Uint8Array((await archive.getZxy(2, 2, 1)).data)]).toEqual([4, 5]);
		expect([...new Uint8Array((await archive.getZxy(1, 1, 0)).data)]).toEqual([6]);
		expect(await archive.getZxy(1, 0, 0)).toBeUndefined();
	});
});
