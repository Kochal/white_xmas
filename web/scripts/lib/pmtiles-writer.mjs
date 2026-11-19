// Minimal PMTiles v3 writer for small raster archives (fixtures only).
// Spec: https://github.com/protomaps/PMTiles/blob/main/spec/v3/spec.md
// Single root directory (no leaf directories), one entry per tile, clustered.
import { gzipSync } from 'node:zlib';
import { zxyToTileId } from 'pmtiles';

export const TileType = { png: 2, jpeg: 3, webp: 4 };
const Compression = { none: 1, gzip: 2 };

function varint(out, value) {
	let v = value;
	while (v >= 0x80) {
		out.push((v % 0x80) | 0x80);
		v = Math.floor(v / 0x80);
	}
	out.push(v);
}

function serializeDirectory(entries) {
	const out = [];
	varint(out, entries.length);
	let last = 0;
	for (const e of entries) {
		varint(out, e.tileId - last);
		last = e.tileId;
	}
	for (const e of entries) varint(out, e.runLength);
	for (const e of entries) varint(out, e.length);
	entries.forEach((e, i) => {
		const prev = entries[i - 1];
		varint(out, i > 0 && e.offset === prev.offset + prev.length ? 0 : e.offset + 1);
	});
	return Buffer.from(out);
}

/**
 * @param {object} opts
 * @param {{z:number,x:number,y:number,data:Uint8Array}[]} opts.tiles
 * @param {number} opts.tileType one of TileType
 * @param {[number,number,number,number]} opts.bounds [w, s, e, n] in degrees
 * @param {object} [opts.metadata]
 * @returns {Buffer}
 */
export function writePmtiles({ tiles, tileType, bounds, metadata = {} }) {
	const sorted = tiles
		.map((t) => ({ ...t, tileId: zxyToTileId(t.z, t.x, t.y) }))
		.sort((a, b) => a.tileId - b.tileId);
	const entries = [];
	let offset = 0;
	for (const t of sorted) {
		entries.push({ tileId: t.tileId, offset, length: t.data.length, runLength: 1 });
		offset += t.data.length;
	}
	const rootDir = gzipSync(serializeDirectory(entries));
	const meta = gzipSync(Buffer.from(JSON.stringify(metadata)));
	const tileData = Buffer.concat(sorted.map((t) => Buffer.from(t.data)));
	const minZoom = Math.min(...sorted.map((t) => t.z));
	const maxZoom = Math.max(...sorted.map((t) => t.z));

	const h = Buffer.alloc(127);
	h.write('PMTiles', 0, 'ascii');
	h[7] = 3;
	const u64 = (pos, v) => h.writeBigUInt64LE(BigInt(v), pos);
	const rootOffset = 127;
	const metaOffset = rootOffset + rootDir.length;
	const leafOffset = metaOffset + meta.length;
	const dataOffset = leafOffset;
	u64(8, rootOffset);
	u64(16, rootDir.length);
	u64(24, metaOffset);
	u64(32, meta.length);
	u64(40, leafOffset);
	u64(48, 0);
	u64(56, dataOffset);
	u64(64, tileData.length);
	u64(72, entries.length);
	u64(80, entries.length);
	u64(88, entries.length);
	h[96] = 1; // clustered
	h[97] = Compression.gzip; // internal compression
	h[98] = Compression.none; // tile compression
	h[99] = tileType;
	h[100] = minZoom;
	h[101] = maxZoom;
	const e7 = (v) => Math.round(v * 1e7);
	h.writeInt32LE(e7(bounds[0]), 102);
	h.writeInt32LE(e7(bounds[1]), 106);
	h.writeInt32LE(e7(bounds[2]), 110);
	h.writeInt32LE(e7(bounds[3]), 114);
	h[118] = minZoom;
	h.writeInt32LE(e7((bounds[0] + bounds[2]) / 2), 119);
	h.writeInt32LE(e7((bounds[1] + bounds[3]) / 2), 123);
	return Buffer.concat([h, rootDir, meta, tileData]);
}
