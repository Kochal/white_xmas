<script lang="ts">
	import { onMount } from 'svelte';
	import type { Layer } from '#lib/data/manifest.ts';
	import type { MapView as View } from '#lib/url-state.ts';

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

	let container: HTMLDivElement;
	let map = $state<import('maplibre-gl').Map | null>(null);
	let styleReady = $state(false);
	let failed = $state<string | null>(null);
	let marker: import('maplibre-gl').Marker | null = null;
	let maplibre: typeof import('maplibre-gl') | null = null;

	function absolute(path: string): string {
		return new URL(`${dataBase}/${path}`, window.location.href).href;
	}

	/** Puts the climate layer under the basemap's labels and boundaries. */
	function firstLabelLayer(m: import('maplibre-gl').Map): string | undefined {
		return m.getStyle().layers.find((l) => l.type === 'symbol')?.id;
	}

	function applyLayer(m: import('maplibre-gl').Map, l: Layer | null) {
		if (m.getLayer(SOURCE)) m.removeLayer(SOURCE);
		if (m.getSource(SOURCE)) m.removeSource(SOURCE);
		if (!l) return;
		m.addSource(SOURCE, {
			type: 'raster',
			url: `pmtiles://${absolute(l.url)}`,
			tileSize: 256
		});
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
			firstLabelLayer(m)
		);
	}

	onMount(() => {
		let disposed = false;
		const dark = window.matchMedia('(prefers-color-scheme: dark)');
		(async () => {
			try {
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
				const m = new ml.Map({
					container,
					style: dark.matches ? STYLE_DARK : STYLE_LIGHT,
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
					applyLayer(m, layer);
				});
				m.on('click', (e) => onselect(e.lngLat.lng, e.lngLat.lat));
				m.on('moveend', () => {
					const c = m.getCenter();
					onviewchange({ zoom: m.getZoom(), lat: c.lat, lon: c.lng });
				});
				m.on('error', (e) => {
					// tile errors for areas without data are expected; log the rest
					if (!String(e.error?.message ?? '').includes('404')) console.warn('[map]', e.error);
				});
				dark.addEventListener('change', onScheme);
				map = m;
			} catch (e) {
				failed = e instanceof Error ? e.message : String(e);
			}
		})();

		function onScheme() {
			if (!map) return;
			styleReady = false;
			map.setStyle(dark.matches ? STYLE_DARK : STYLE_LIGHT);
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
	aria-label="Map of white Christmas probability. Click anywhere to see that place's history."
></div>
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
