<script lang="ts">
	import { onMount } from 'svelte';
	import type { BoundaryCollection, RegionRow } from '#lib/data/admin1.ts';
	import type { Layer } from '#lib/data/manifest.ts';
	import type { MapView as View } from '#lib/url-state.ts';
	import { climateLayerBefore, slimBasemap, withClimateLayer } from './basemap.ts';
	import {
		BASEMAP_STATE_LAYERS,
		DARK,
		FILL_LAYER,
		LABELS_SOURCE,
		LIGHT,
		REGIONS_SOURCE,
		SELECTED_FILL,
		SELECTED_LINE,
		labelCollection,
		regionLayers,
		toggledLayerIds
	} from './regions-layer.ts';

	/** The states-and-provinces layer (contract v1.6): outlines, rows for the labels, toggle. */
	export interface RegionsProp {
		boundaries: BoundaryCollection | null;
		rows: RegionRow[];
		/** Borders, labels and hover on; the selected outline shows either way. */
		show: boolean;
		/** Region id (`DE-BY`) to outline, if any. */
		selected: string | null;
	}

	interface Props {
		dataBase: string;
		layer: Layer | null;
		view: View;
		selected: { lon: number; lat: number } | null;
		attribution: string;
		onselect: (lon: number, lat: number) => void;
		onviewchange: (view: View) => void;
		regions?: RegionsProp;
		/** A click (or Enter at the centre) on a region while the layer is shown. */
		onregionselect?: (id: string) => void;
	}

	let {
		dataBase,
		layer,
		view,
		selected,
		attribution,
		onselect,
		onviewchange,
		regions,
		onregionselect
	}: Props = $props();

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
	/** Name under the pointer while hovering a region (desktop). */
	let hoverName = $state<string | null>(null);
	let hoverId: number | null = null;

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
	 * Adds the region sources and layers once the outlines have arrived, and keeps their
	 * visibility, outline and the basemap's own state layers in step. Safe to call again.
	 */
	function applyRegions(m: import('maplibre-gl').Map, r: RegionsProp | undefined) {
		if (!r || !r.boundaries) return;
		const style = m.getStyle();
		const dark = window.matchMedia('(prefers-color-scheme: dark)').matches;
		const specs = regionLayers(dark ? DARK : LIGHT, !!style.glyphs);
		if (!m.getSource(REGIONS_SOURCE)) {
			m.addSource(REGIONS_SOURCE, {
				type: 'geojson',
				data: r.boundaries as unknown as import('maplibre-gl').GeoJSONSourceSpecification['data']
			});
			m.addSource(LABELS_SOURCE, {
				type: 'geojson',
				data: labelCollection(
					r.rows
				) as unknown as import('maplibre-gl').GeoJSONSourceSpecification['data']
			});
		}
		for (const spec of specs) if (!m.getLayer(spec.id)) m.addLayer(spec);
		const toggled = new Set(toggledLayerIds(specs));
		for (const spec of specs)
			m.setLayoutProperty(
				spec.id,
				'visibility',
				toggled.has(spec.id) && !r.show ? 'none' : 'visible'
			);
		const filter = [
			'==',
			['get', 'id'],
			r.selected ?? ''
		] as import('maplibre-gl').FilterSpecification;
		for (const id of [SELECTED_FILL, SELECTED_LINE]) m.setFilter(id, filter);
		// our outlines replace the basemap's own state borders and names
		for (const id of BASEMAP_STATE_LAYERS)
			if (m.getLayer(id)) m.setLayoutProperty(id, 'visibility', r.show ? 'none' : 'visible');
		if (!r.show) clearHover(m);
	}

	function clearHover(m: import('maplibre-gl').Map) {
		if (hoverId !== null && m.getSource(REGIONS_SOURCE))
			m.setFeatureState({ source: REGIONS_SOURCE, id: hoverId }, { hover: false });
		hoverId = null;
		hoverName = null;
	}

	/** The region id (`DE-BY`) drawn at a screen point, if the layer is on. */
	function regionAt(
		m: import('maplibre-gl').Map,
		point: import('maplibre-gl').PointLike
	): string | null {
		if (!regions?.show || !m.getLayer(FILL_LAYER)) return null;
		const f = m.queryRenderedFeatures(point, { layers: [FILL_LAYER] })[0];
		const id = f?.properties?.id;
		return typeof id === 'string' ? id : null;
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
				let styleTimer: ReturnType<typeof setTimeout> | undefined;
				m.on('style.load', () => {
					styleReady = true;
					if (m.getStyle().sources.openmaptiles) {
						// the basemap arrived, even if late: clear any "unavailable" notice
						basemapLoaded = true;
						basemapDown = false;
						clearTimeout(styleTimer);
					}
					applyLayer(m, layer);
					applyRegions(m, regions);
				});
				const loadBasemap = () => {
					basemapLoaded = false;
					// if the basemap style hasn't arrived after 12 s, say so (the data still shows)
					clearTimeout(styleTimer);
					styleTimer = setTimeout(() => {
						if (!basemapLoaded) basemapDown = true;
					}, 12_000);
					m.setStyle(dark.matches ? STYLE_DARK : STYLE_LIGHT, {
						transformStyle: (prev, next) => withClimateLayer(prev, slimBasemap(next), SOURCE)
					});
				};
				m.once('load', loadBasemap);
				m.on('click', (e) => {
					const id = regionAt(m, e.point);
					if (id && onregionselect) onregionselect(id);
					else onselect(e.lngLat.lng, e.lngLat.lat);
				});
				// hover highlight and name tooltip (mouse only; touch has no hover)
				m.on('mousemove', (e) => {
					if (!regions?.show || !m.getLayer(FILL_LAYER)) return;
					const f = m.queryRenderedFeatures(e.point, { layers: [FILL_LAYER] })[0];
					const fid = typeof f?.id === 'number' ? f.id : null;
					m.getCanvas().style.cursor = fid === null ? '' : 'pointer';
					if (fid === hoverId) return;
					if (hoverId !== null)
						m.setFeatureState({ source: REGIONS_SOURCE, id: hoverId }, { hover: false });
					hoverId = fid;
					if (fid !== null) m.setFeatureState({ source: REGIONS_SOURCE, id: fid }, { hover: true });
					const name = fid === null ? undefined : regions.rows[fid]?.name;
					hoverName = name ?? null;
				});
				m.getCanvas().addEventListener('mouseleave', () => {
					m.getCanvas().style.cursor = '';
					clearHover(m);
				});
				// keyboard: arrows pan (built in), Enter or Space selects the point at the centre
				m.getCanvas().addEventListener('keydown', (e) => {
					if (e.key !== 'Enter' && e.key !== ' ') return;
					e.preventDefault();
					const c = m.getCenter();
					const id = regionAt(m, m.project(c));
					if (id && onregionselect) onregionselect(id);
					else onselect(c.lng, c.lat);
				});
				m.on('moveend', () => {
					const c = m.getCenter();
					onviewchange({ zoom: m.getZoom(), lat: c.lat, lon: c.lng });
				});
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

	// add, show, hide and outline the regions when the outlines arrive or the controls change
	$effect(() => {
		const r = regions;
		// read the fields here so the effect re-runs when they change
		void [r?.boundaries, r?.show, r?.selected, r?.rows];
		if (map && styleReady) applyRegions(map, r);
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

	/** Zoom to a region's bounding box (west, south, east, north), clear of the open panel. */
	export function fitBounds(bbox: [number, number, number, number]) {
		if (!map) return;
		const wide = window.innerWidth > 720;
		map.fitBounds(
			[
				[bbox[0], bbox[1]],
				[bbox[2], bbox[3]]
			],
			{
				padding: wide
					? { top: 40, bottom: 40, left: 360, right: 420 }
					: { top: 110, bottom: Math.round(window.innerHeight * 0.45), left: 24, right: 24 },
				maxZoom: 8,
				essential: true
			}
		);
	}

	/** Fly to a coordinate (used by search). */
	export function flyTo(lon: number, lat: number, zoom = 7) {
		map?.flyTo({ center: [lon, lat], zoom: Math.max(map.getZoom(), zoom), essential: true });
	}
</script>

<div
	class="map"
	bind:this={container}
	role="region"
	aria-label={regions?.show
		? 'Map of white Christmas probability with state and province borders. Click a region, or use the arrow keys and press Enter, to see the state or province at the centre.'
		: 'Map of white Christmas probability. Click anywhere, or use the arrow keys and press Enter, to see the history of the point at the centre.'}
></div>
{#if hoverName}
	<p class="region-tip" role="presentation">{hoverName}</p>
{/if}
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
	.region-tip {
		position: absolute;
		z-index: 4;
		left: 50%;
		bottom: 12px;
		transform: translateX(-50%);
		margin: 0;
		padding: 3px 10px;
		font-size: 0.82rem;
		background: var(--surface);
		border-radius: 6px;
		box-shadow: var(--shadow);
		pointer-events: none;
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
