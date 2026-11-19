/** Network hints (Network Information API, where the browser supports it). */
export interface ConnectionLike {
	saveData?: boolean;
	effectiveType?: string;
}

/**
 * Whether optional prefetches are welcome: not when the user asked to save data, and not on
 * 2G-class connections. Unknown connections (most browsers) allow it.
 */
export function allowsPrefetch(connection: ConnectionLike | undefined): boolean {
	if (!connection) return true;
	if (connection.saveData) return false;
	return connection.effectiveType !== '2g' && connection.effectiveType !== 'slow-2g';
}
