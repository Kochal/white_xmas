<script lang="ts">
	import { onMount } from 'svelte';
	import type { Layer } from '#lib/data/manifest.ts';
	import type { MapView as View } from '#lib/url-state.ts';
	import { climateLayerBefore, slimBasemap, withClimateLayer } from './basemap.ts';

	interface Props {
		dataBase: string;
		layer: Layer | null;
		view: View;
		selected: { lon: number; lat: number } | null;
		attribution: string;
		onselect: (lon: number, lat: number) => void;
		onviewchange: (view: View) => void;
	}

	let { dataBase, layer, view, selected, attribution, onselect, onviewchange }: Props = $props();

	const STYLE_LIGHT = 'https://tiles.openfreemap.org/styles/positron';
	const STYLE_DARK = 'https://tiles.openfreemap.org/styles/dark';
	const SOURCE = 'wx-layer';
	/** Plain background used when the basemap style can't be loaded, so the data still shows. */
	const fallbackStyle = (dark: boolean): import('maplibre-gl').StyleSpecification => ({
		version: 8,
		sources: {},
		layers: [
			{
				id: 'background',
				type: 'background',
				paint: { 'background-color': dark ? '#1b2230' : '#e6ebf1' }
			}
		]
	});

	let container: HTMLDivElement;
	let map = $state<import('maplibre-gl').Map | null>(null);
	let styleReady = $state(false);
	let failed = $state<string | null>(null);
	let basemapDown = $state(false);
	let basemapLoaded = false;
	let marker: import('maplibre-gl').Marker | null = null;
	let maplibre: typeof import('maplibre-gl') | null = null;

	function absolute(path: string): string {
		return new URL(`${dataBase}/${path}`, window.location.href).href;
	}

	/** Adds (or swaps) the climate layer; a no-op when it already shows this layer. */
	function applyLayer(m: import('maplibre-gl').Map, l: Layer | null) {
		const url = l ? `pmtiles://${absolute(l.url)}` : null;
		const current = m.getSource(SOURCE) as { url?: string } | undefined;
		if (current && url && current.url === url && m.getLayer(SOURCE)) return;
		if (m.getLayer(SOURCE)) m.removeLayer(SOURCE);
		if (m.getSource(SOURCE)) m.removeSource(SOURCE);
		if (!l || !url) return;
		m.addSource(SOURCE, { type: 'raster', url, tileSize: 256 });
		m.addLayer(
			{
				id: SOURCE,
				type: 'raster',
				source: SOURCE,
				paint: {
					'raster-opacity': 0.82,
					'raster-resampling': 'nearest',
					'raster-fade-duration': 150
				}
			},
			climateLayerBefore(m.getStyle().layers)
		);
	}

	/**
	 * Resolves once the page has loaded and painted. MapLibre (~1 MB) is fetched only then,
	 * so its download never competes with the first paint on slow connections.
	 */
	function afterFirstPaint(): Promise<void> {
		const loaded =
			document.readyState === 'complete'
				? Promise.resolve()
				: new Promise<void>((r) => window.addEventListener('load', () => r(), { once: true }));
		return loaded.then(
			() => new Promise<void>((r) => requestAnimationFrame(() => requestAnimationFrame(() => r())))
		);
	}

	onMount(() => {
		let disposed = false;
		let reloadBasemap: (() => void) | null = null;
		const dark = window.matchMedia('(prefers-color-scheme: dark)');
		(async () => {
			try {
				await afterFirstPaint();
				if (disposed) return;
				const [ml, { Protocol }, worker] = await Promise.all([
					import('maplibre-gl'),
					import('pmtiles'),
					import('maplibre-gl/dist/maplibre-gl-worker.mjs?url'),
					// loaded with the map, so it doesn't block the first paint
					import('maplibre-gl/dist/maplibre-gl.css')
				]);
				if (disposed) return;
				maplibre = ml;
				ml.setWorkerUrl(worker.default);
				const protocol = new Protocol();
				ml.addProtocol('pmtiles', protocol.tile);
				// Start with a plain background and the climate layer; the (slimmed) basemap
				// follows once the map has loaded, so the data shows first and the first
				// render stays cheap on phones.
				const m = new ml.Map({
					container,
					style: fallbackStyle(dark.matches),
					fadeDuration: 0,
					pixelRatio: Math.min(window.devicePixelRatio || 1, 2),
					center: [view.lon, view.lat],
					zoom: view.zoom,
					minZoom: 1,
					maxZoom: 10,
					renderWorldCopies: true,
					attributionControl: { compact: true, customAttribution: attribution },
					cooperativeGestures: false
				});
				m.addControl(new ml.NavigationControl({ showCompass: false }), 'bottom-right');
				m.on('style.load', () => {
					styleReady = true;
					if (m.getStyle().sources.openmaptiles) basemapLoaded = true;
					applyLayer(m, layer);
				});
				const loadBasemap = () => {
					basemapLoaded = false;
					m.setStyle(dark.matches ? STYLE_DARK : STYLE_LIGHT, {
						transformStyle: (prev, next) => withClimateLayer(prev, slimBasemap(next), SOURCE)
					});
				};
				m.once('load', loadBasemap);
				m.on('click', (e) => onselect(e.lngLat.lng, e.lngLat.lat));
				// keyboard: arrows pan (built in), Enter or Space selects the point at the centre
				m.getCanvas().addEventListener('keydown', (e) => {
					if (e.key !== 'Enter' && e.key !== ' ') return;
					e.preventDefault();
					const c = m.getCenter();
					onselect(c.lng, c.lat);
				});
				m.on('moveend', () => {
					const c = m.getCenter();
					onviewchange({ zoom: m.getZoom(), lat: c.lat, lon: c.lng });
				});
				// if the basemap style can't be fetched, keep the plain background and say so
				const styleTimer = setTimeout(() => {
					if (!basemapLoaded) basemapDown = true;
				}, 12_000);
				m.on('error', (e) => {
					if (!basemapLoaded && !(e as { sourceId?: string }).sourceId) {
						basemapDown = true;
						clearTimeout(styleTimer);
						// setStyle failed: restore the background style with the climate layer
						m.setStyle(fallbackStyle(dark.matches), {
							transformStyle: (prev, next) => withClimateLayer(prev, next, SOURCE)
						});
					}
					// tile errors for areas without data are expected; log the rest
					else if (!String(e.error?.message ?? '').includes('404')) console.warn('[map]', e.error);
				});
				reloadBasemap = loadBasemap;
				dark.addEventListener('change', onScheme);
				map = m;
			} catch (e) {
				failed = e instanceof Error ? e.message : String(e);
			}
		})();

		function onScheme() {
			if (!map) return;
			if (basemapDown) map.setStyle(fallbackStyle(dark.matches));
			else reloadBasemap?.();
		}

		return () => {
			disposed = true;
			dark.removeEventListener('change', onScheme);
			map?.remove();
		};
	});

	// switch the climate layer when the selection changes
	$effect(() => {
		const l = layer;
		if (map && styleReady) applyLayer(map, l);
	});

	// keep the marker on the selected cell
	$effect(() => {
		const s = selected;
		if (!map || !maplibre) return;
		if (!s) {
			marker?.remove();
			marker = null;
			return;
		}
		if (!marker) marker = new maplibre.Marker({ color: '#c0392b' });
		marker.setLngLat([s.lon, s.lat]).addTo(map);
	});

	/** Fly to a coordinate (used by search). */
	export function flyTo(lon: number, lat: number, zoom = 7) {
		map?.flyTo({ center: [lon, lat], zoom: Math.max(map.getZoom(), zoom), essential: true });
	}
</script>

<div
	class="map"
	bind:this={container}
	role="region"
	aria-label="Map of white Christmas probability. Click anywhere, or use the arrow keys and press Enter, to see the history of the point at the centre."
></div>
{#if basemapDown}
	<p class="basemap-note" role="status">The background map is unavailable right now.</p>
{/if}
{#if failed}
	<p class="map-error" role="alert">
		The map could not start ({failed}). Search still works, and the place panel shows the data.
	</p>
{/if}

<style>
	.map {
		position: absolute;
		inset: 0;
		background: var(--surface-2);
	}
	.basemap-note {
		position: absolute;
		z-index: 4;
		left: 50%;
		bottom: 12px;
		transform: translateX(-50%);
		margin: 0;
		padding: 4px 10px;
		font-size: 0.8rem;
		background: var(--surface);
		border-radius: 6px;
		box-shadow: var(--shadow);
	}
	.map-error {
		position: absolute;
		top: 50%;
		left: 50%;
		transform: translate(-50%, -50%);
		max-width: 320px;
		padding: 12px 16px;
		background: var(--surface);
		border-radius: var(--radius);
		box-shadow: var(--shadow);
	}
	:global(.maplibregl-ctrl-attrib) {
		font-size: 11px;
	}
</style>
