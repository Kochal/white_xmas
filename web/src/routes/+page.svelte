<script lang="ts">
	import { onMount, tick } from 'svelte';
	import { goto } from '$app/navigation';
	import { DATA_BASE } from '#lib/config.ts';
	import type { Layer, LayerKind, Manifest } from '#lib/data/manifest.ts';
	import type { Place } from '#lib/data/places.ts';
	import type { CellLookup, DataSource } from '#lib/data/source.ts';
	import { getDataSource } from '#lib/data/client.ts';
	import PlaceSearch from '#lib/components/PlaceSearch.svelte';
	import Legend from '#lib/map/Legend.svelte';
	import MapView from '#lib/map/MapView.svelte';
	import {
		KIND_LABELS,
		availableKinds,
		normalizeSelection,
		periodOptions,
		resolveLayer,
		type Selection
	} from '#lib/map/layers.ts';
	import PlacePanel from '#lib/panel/PlacePanel.svelte';
	import type { PlaceLabel } from '#lib/panel/types.ts';
	import Seo from '#lib/components/Seo.svelte';
	import { parseUrlState, serializeUrlState, type MapView as View } from '#lib/url-state.ts';

	const DEFAULT_VIEW: View = { zoom: 3, lat: 48, lon: 10 };
	const ERA5_ATTRIBUTION =
		'<a href="https://cds.climate.copernicus.eu/datasets/derived-era5-land-daily-statistics" target="_blank" rel="noopener">ERA5-Land</a> (Copernicus)';

	let ds = $state<DataSource | null>(null);
	let manifest = $state<Manifest | null>(null);
	let fatal = $state<string | null>(null);
	let selection = $state<Selection>({ definition: '', kind: 'probability', period: '' });
	let view = $state<View>(DEFAULT_VIEW);
	let at = $state<{ lon: number; lat: number } | null>(null);
	let label = $state<PlaceLabel | null>(null);
	let lookup = $state<CellLookup | null>(null);
	let loading = $state(false);
	let lookupError = $state<string | null>(null);
	let panelExpanded = $state(false);
	let controlsOpen = $state(false);
	let ready = $state(false);
	let mapView = $state<ReturnType<typeof MapView> | null>(null);

	const layer = $derived<Layer | null>(manifest ? resolveLayer(manifest, selection) : null);
	const kinds = $derived<LayerKind[]>(manifest ? availableKinds(manifest) : []);
	const periods = $derived(
		manifest ? periodOptions(manifest, selection.kind, selection.definition) : []
	);
	const colormap = $derived(
		layer && manifest ? (manifest.colormaps[layer.colormap] ?? null) : null
	);
	const definition = $derived(manifest?.definitions.find((d) => d.id === selection.definition));
	const legendTitle = $derived.by(() => {
		if (!layer || !definition) return definition?.label ?? '';
		return {
			probability: 'Chance of a white Christmas',
			change: 'Change in chance',
			trend: 'Trend in chance',
			projection: 'Projected chance'
		}[layer.kind];
	});
	const legendSubtitle = $derived.by(() => {
		if (!definition) return '';
		const period = periods.find((p) => p.value === selection.period)?.label ?? '';
		return [period, definition.short].filter(Boolean).join(' · ');
	});
	const fixture = $derived(manifest?.data_version.includes('fixture') ?? false);
	const glaciers = $derived(manifest?.glacier_style === 'hatched');

	let lookupSeq = 0;
	async function select(lon: number, lat: number, placeLabel: PlaceLabel | null, nearestLand = 0) {
		if (!ds) return;
		at = { lon, lat };
		label = placeLabel;
		loading = true;
		lookupError = null;
		const seq = ++lookupSeq;
		try {
			const r = await ds.lookup(lon, lat, { nearestLand });
			if (seq === lookupSeq) lookup = r;
		} catch (e) {
			if (seq === lookupSeq) lookupError = e instanceof Error ? e.message : String(e);
		} finally {
			if (seq === lookupSeq) loading = false;
		}
	}

	function placeLabel(p: Place): PlaceLabel {
		let country = p.country;
		try {
			country = new Intl.DisplayNames(['en'], { type: 'region' }).of(p.country) ?? p.country;
		} catch {
			/* keep the code */
		}
		return { name: p.name, detail: [p.admin1, country].filter(Boolean).join(', ') };
	}

	function pickPlace(p: Place) {
		select(p.lon, p.lat, placeLabel(p), 2);
		mapView?.flyTo(p.lon, p.lat, 7);
		controlsOpen = false;
	}

	function closePanel() {
		at = null;
		label = null;
		lookup = null;
		lookupError = null;
		panelExpanded = false;
	}

	function setSelection(partial: Partial<Selection>) {
		if (!manifest) return;
		selection = normalizeSelection(manifest, { ...selection, ...partial });
	}

	// keep the URL in sync (debounced), so every view is shareable
	let urlTimer: ReturnType<typeof setTimeout> | undefined;
	$effect(() => {
		const qs = serializeUrlState({
			view,
			selection,
			at: at ?? undefined,
			place: label?.name
		});
		if (!ready) return;
		clearTimeout(urlTimer);
		urlTimer = setTimeout(() => {
			const url = `${window.location.pathname}${qs}`;
			if (url !== `${window.location.pathname}${window.location.search}`) {
				// The URL comes from window.location.pathname, which already carries the base path.
				// eslint-disable-next-line svelte/no-navigation-without-resolve
				goto(url, { replace: true, shallow: true }).catch(() => {});
			}
		}, 250);
	});

	onMount(() => {
		const url = parseUrlState(new URLSearchParams(window.location.search));
		if (url.view) view = url.view;
		getDataSource()
			.then(async (source) => {
				ds = source;
				manifest = source.manifest;
				selection = normalizeSelection(source.manifest, url.selection);
				await tick();
				ready = true;
				if (url.at) {
					let restored: PlaceLabel | null = url.place ? { name: url.place, detail: '' } : null;
					// restore the place's region and country from places.json when it matches
					if (url.place) {
						try {
							const { places } = await source.places();
							const p = places.find(
								(x) =>
									x.name === url.place &&
									Math.abs(x.lat - url.at!.lat) < 0.01 &&
									Math.abs(x.lon - url.at!.lon) < 0.01
							);
							if (p) restored = placeLabel(p);
						} catch {
							/* the label stays as given */
						}
					}
					select(url.at.lon, url.at.lat, restored, restored ? 2 : 0);
				}
			})
			.catch((e: Error) => {
				fatal = e.message;
			});
		return () => clearTimeout(urlTimer);
	});
</script>

<Seo
	title="White Christmas: how likely is snow at Christmas where you live?"
	description="Look up how often there has been snow on the ground at Christmas anywhere on Earth since 1950, how that has changed, and how it changes in a warmer world."
/>

<svelte:head>
	<link rel="preload" as="fetch" href={`${DATA_BASE}/manifest.json`} crossorigin="anonymous" />
	<link rel="preconnect" href="https://tiles.openfreemap.org" crossorigin="anonymous" />
</svelte:head>

<div class="stage" class:with-panel={!!at}>
	{#if manifest}
		<MapView
			bind:this={mapView}
			dataBase={DATA_BASE}
			{layer}
			{view}
			selected={at}
			attribution={ERA5_ATTRIBUTION}
			onselect={(lon, lat) => select(lon, lat, null)}
			onviewchange={(v) => (view = v)}
		/>
	{/if}

	<div class="overlay-top">
		<div class="controls" class:open={controlsOpen}>
			<h1 class="intro">How likely is a white Christmas where you live?</h1>
			<div class="search-row">
				<div class="search-wrap">
					<PlaceSearch
						loadPlaces={async () => (ds ? (await ds.places()).places : [])}
						onpick={pickPlace}
					/>
				</div>
				<button
					class="layers-toggle"
					aria-expanded={controlsOpen}
					aria-controls="layer-controls"
					onclick={() => (controlsOpen = !controlsOpen)}
				>
					<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true">
						<path
							d="M12 3l9 5-9 5-9-5 9-5zm-9 9l9 5 9-5M3 16l9 5 9-5"
							fill="none"
							stroke="currentColor"
							stroke-width="1.8"
							stroke-linejoin="round"
						/>
					</svg>
					<span class="visually-hidden">Map layers</span>
				</button>
			</div>

			{#if manifest}
				<div id="layer-controls" class="layer-controls">
					<fieldset class="kinds">
						<legend class="visually-hidden">Map layer</legend>
						{#each kinds as k (k)}
							<label class:checked={selection.kind === k}>
								<input
									type="radio"
									name="kind"
									value={k}
									checked={selection.kind === k}
									onchange={() => setSelection({ kind: k, period: '' })}
								/>
								{KIND_LABELS[k]}
							</label>
						{/each}
					</fieldset>
					<div class="selects">
						<label>
							<span>Definition</span>
							<select
								value={selection.definition}
								onchange={(e) => setSelection({ definition: e.currentTarget.value })}
							>
								{#each manifest.definitions as d (d.id)}
									<option value={d.id}>{d.label}</option>
								{/each}
							</select>
						</label>
						<label>
							<span>{selection.kind === 'projection' ? 'Warming' : 'Period'}</span>
							<select
								value={selection.period}
								disabled={periods.length === 0}
								onchange={(e) => setSelection({ period: e.currentTarget.value })}
							>
								{#each periods as p (p.value)}
									<option value={p.value}>{p.label}</option>
								{:else}
									<option value="">No map layer</option>
								{/each}
							</select>
						</label>
					</div>
				</div>
			{/if}
		</div>
		{#if fixture}
			<p class="fixture" role="note">Fixture data: the values are fake, for development only.</p>
		{/if}
	</div>

	{#if manifest}
		<div class="overlay-legend" class:hidden-mobile={!!at}>
			<Legend {layer} {colormap} title={legendTitle} subtitle={legendSubtitle} {glaciers} />
		</div>
	{/if}

	{#if manifest && at}
		<PlacePanel
			{manifest}
			{lookup}
			{loading}
			error={lookupError}
			{label}
			{selection}
			expanded={panelExpanded}
			onclose={closePanel}
			ontoggle={() => (panelExpanded = !panelExpanded)}
			ondefinition={(id) => setSelection({ definition: id })}
		/>
	{/if}

	{#if fatal}
		<div class="fatal" role="alert">
			<h2>The data isn't available yet</h2>
			<p>
				The map data hasn't been published here yet, or it couldn't be loaded. Please try again
				later.
			</p>
			<p class="muted small">{fatal}</p>
		</div>
	{:else if !manifest}
		<p class="loading muted" aria-live="polite">Loading the map…</p>
	{/if}
</div>

<style>
	.stage {
		position: relative;
		height: calc(100dvh - var(--header-h));
		min-height: 420px;
		overflow: hidden;
		background: var(--surface-2);
	}
	@media (min-width: 721px) {
		.stage.with-panel :global(.maplibregl-ctrl-bottom-right) {
			right: 400px;
		}
	}
	.overlay-top {
		position: absolute;
		z-index: 8;
		top: 12px;
		left: 12px;
		width: 340px;
		max-width: calc(100% - 24px);
	}
	.controls {
		padding: 10px;
		background: var(--surface);
		border-radius: var(--radius);
		box-shadow: var(--shadow);
	}
	.intro {
		margin: 0 2px 8px;
		font-size: 1.02rem;
		line-height: 1.3;
		font-weight: 650;
	}
	.search-row {
		display: flex;
		gap: 8px;
	}
	.search-wrap {
		flex: 1;
		min-width: 0;
	}
	.layers-toggle {
		display: none;
		flex: none;
		width: 42px;
		align-items: center;
		justify-content: center;
		border: 1px solid var(--line);
		border-radius: 8px;
		background: var(--surface);
		color: var(--text);
		cursor: pointer;
	}
	.layers-toggle[aria-expanded='true'] {
		background: var(--accent-soft);
	}
	.layer-controls {
		margin-top: 10px;
	}
	.kinds {
		display: flex;
		margin: 0;
		padding: 2px;
		border: 0;
		background: var(--surface-2);
		border-radius: 8px;
	}
	.kinds label {
		flex: 1;
		position: relative;
		padding: 6px 4px;
		text-align: center;
		font-size: 0.86rem;
		border-radius: 6px;
		cursor: pointer;
		color: var(--muted);
	}
	.kinds label.checked {
		background: var(--surface);
		color: var(--text);
		font-weight: 600;
		box-shadow: 0 1px 2px rgb(0 0 0 / 0.12);
	}
	.kinds label:has(input:focus-visible) {
		outline: 2px solid var(--accent);
	}
	.kinds input {
		position: absolute;
		opacity: 0;
		inset: 0;
		margin: 0;
		cursor: pointer;
	}
	.selects {
		display: grid;
		grid-template-columns: 1fr;
		gap: 8px;
		margin-top: 8px;
	}
	.selects label {
		display: grid;
		grid-template-columns: 72px 1fr;
		align-items: center;
		gap: 8px;
		font-size: 0.75rem;
		color: var(--muted);
		min-width: 0;
	}
	.selects select {
		width: 100%;
		padding: 6px 6px;
		font: inherit;
		font-size: 0.86rem;
		color: var(--text);
		background: var(--surface);
		border: 1px solid var(--line);
		border-radius: 6px;
	}
	.fixture {
		margin: 8px 0 0;
		padding: 6px 10px;
		font-size: 0.8rem;
		color: var(--warn);
		background: var(--surface);
		border-radius: 8px;
		box-shadow: var(--shadow);
	}
	.overlay-legend {
		position: absolute;
		z-index: 5;
		left: 12px;
		bottom: 28px;
	}
	.fatal,
	.loading {
		position: absolute;
		z-index: 9;
		top: 50%;
		left: 50%;
		transform: translate(-50%, -50%);
		max-width: min(420px, calc(100% - 32px));
		margin: 0;
	}
	.fatal {
		padding: 16px 20px;
		background: var(--surface);
		border-radius: var(--radius);
		box-shadow: var(--shadow);
	}
	.fatal h2 {
		margin: 0 0 6px;
		font-size: 1.1rem;
	}
	.small {
		font-size: 0.8rem;
	}

	@media (max-width: 720px) {
		.overlay-top {
			top: 8px;
			left: 8px;
			right: 8px;
			width: auto;
			max-width: none;
		}
		.controls {
			padding: 8px;
		}
		.intro {
			font-size: 0.92rem;
			margin-bottom: 6px;
		}
		.layers-toggle {
			display: inline-flex;
		}
		.layer-controls {
			display: none;
		}
		.controls.open .layer-controls {
			display: block;
		}
		.overlay-legend {
			left: 8px;
			bottom: 8px;
		}
		.overlay-legend.hidden-mobile {
			display: none;
		}
	}
</style>
