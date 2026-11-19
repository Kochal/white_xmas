/** One shared DataSource per page load (browser only). */
import { DATA_BASE } from '#lib/config.ts';
import { DataSource } from './source.ts';

let source: Promise<DataSource> | null = null;

export function getDataSource(): Promise<DataSource> {
	source ??= DataSource.open(DATA_BASE);
	source.catch(() => (source = null));
	return source;
}
