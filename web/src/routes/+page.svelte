<script lang="ts">
	import { onMount, tick } from 'svelte';
	import { goto } from '$app/navigation';
	import { DATA_BASE } from '#lib/config.ts';
	import type { Admin1Index, CountryFile, RegionRow } from '#lib/data/admin1.ts';
	import type { Layer, LayerKind, Manifest } from '#lib/data/manifest.ts';
	import type { Place } from '#lib/data/places.ts';
	import type { CellLookup, DataSource } from '#lib/data/source.ts';
	import { getDataSource } from '#lib/data/client.ts';
	import { allowsPrefetch, type ConnectionLike } from '#lib/net.ts';
	import PlaceSearch from '#lib/components/PlaceSearch.svelte';
	import Legend from '#lib/map/Legend.svelte';
	import MapView from '#lib/map/MapView.svelte';
	import { thresholdById, thresholdShortLabel } from '#lib/data/manifest.ts';
	import {
		FUTURE_MODE_LABELS,
		KIND_LABELS,
		availableKinds,
		futureModes,
		isFuture,
		normalizeSelection,
		warmingLevelNote,
		periodOptions,
		resolveLayer,
		thresholdHasLayers,
		type Selection
	} from '#lib/map/layers.ts';
	import PlacePanel from '#lib/panel/PlacePanel.svelte';
	import type { PlaceLabel } from '#lib/panel/types.ts';
	import Seo from '#lib/components/Seo.svelte';
	import {
		parseRegionHash,
		rejectedRegionHash,
		parseUrlState,
		serializeUrl,
		type MapView as View
	} from '#lib/url-state.ts';

	const DEFAULT_VIEW: View = { zoom: 3, lat: 48, lon: 10 };
	const ERA5_ATTRIBUTION =
		'<a href="https://cds.climate.copernicus.eu/datasets/derived-era5-land-daily-statistics" target="_blank" rel="noopener">ERA5-Land</a> (Copernicus)';

	let ds = $state.raw<DataSource | null>(null);
	let manifest = $state.raw<Manifest | null>(null);
	let fatal = $state<string | null>(null);
	let selection = $state<Selection>({
		definition: '',
		kind: 'probability',
		period: '',
		threshold: ''
	});
	let view = $state<View>(DEFAULT_VIEW);
	let at = $state<{ lon: number; lat: number } | null>(null);
	let label = $state<PlaceLabel | null>(null);
	let lookup = $state.raw<CellLookup | null>(null);
	let loading = $state(false);
	let lookupError = $state<string | null>(null);
	let panelExpanded = $state(false);
	let controlsOpen = $state(false);
	let ready = $state(false);
	let mapView = $state<ReturnType<typeof MapView> | null>(null);

	// states and provinces (contract v1.6): all of it loads lazily, never with the first paint
	/** The user's "States and provinces" switch: borders, names and hover on the whole map. */
	let regionsOn = $state(false);
	let regionIndex = $state.raw<Admin1Index | null>(null);
	let indexLoading = $state(false);
	let outlineStatus = $state<'idle' | 'loading' | 'ready' | 'error'>('idle');
	/** Save-Data and 2G users don't get the 1.4 MB outlines just to see one region's edge. */
	let outlinesOk = true;
	let regionId = $state<string | null>(null);
	let regionCountry = $state.raw<CountryFile | null>(null);
	let regionError = $state<string | null>(null);
	/** A status line for region problems; outside the (on phones folded) layer controls. */
	let regionsNote = $state<string | null>(null);
	/** The region panel's code (charts, statistics) loads with the first region, not the page. */
	let RegionPanel = $state.raw<typeof import('#lib/panel/RegionPanel.svelte').default | null>(null);
	const hasRegions = $derived(!!manifest?.admin1?.available);
	const regionRow = $derived<RegionRow | null>(
		regionIndex && regionId ? (regionIndex.rows.find((r) => r.id === regionId) ?? null) : null
	);
	const hasPanel = $derived(!!at || !!regionId);
	/** Outlines are fetched for the switch, or for the selected region's outline. */
	const wantOutlines = $derived(regionsOn || (!!regionId && outlinesOk));
	const regionsProp = $derived({
		// the index comes first: the label points are built from its rows when the source is added
		boundariesPath: wantOutlines && regionIndex ? (manifest?.admin1?.boundaries ?? null) : null,
		rows: regionIndex?.rows ?? [],
		show: regionsOn,
		selected: regionId
	});

	const layer = $derived<Layer | null>(manifest ? resolveLayer(manifest, selection) : null);
	const kinds = $derived<LayerKind[]>(
		manifest ? availableKinds(manifest, selection.definition, selection.threshold) : []
	);
	const modes = $derived(
		manifest ? futureModes(manifest, selection.definition, selection.threshold) : []
	);
	const threshold = $derived(manifest ? thresholdById(manifest, selection.threshold) : null);
	const rawThreshold = $derived(manifest?.thresholds.find((t) => !t.default) ?? null);
	const rawUnavailable = $derived(
		!!manifest &&
			!!rawThreshold &&
			!thresholdHasLayers(manifest, rawThreshold.id, selection.definition)
	);
	const rawDefinitions = $derived(
		manifest && rawThreshold
			? manifest.definitions
					.filter((d) => thresholdHasLayers(manifest!, rawThreshold.id, d.id))
					.map((d) => d.label)
			: []
	);
	/** Projections exist for the calibrated threshold only (contract v1.5). */
	const futureNote = $derived(
		!!manifest &&
			!!threshold &&
			!threshold.default &&
			futureModes(manifest, selection.definition).length > 0
	);
	const tabOf = (k: LayerKind): LayerKind => (isFuture(k) ? 'projection' : k);
	const levelNote = $derived(
		manifest && isFuture(selection.kind) ? warmingLevelNote(manifest, selection.period) : ''
	);
	const periods = $derived(
		manifest
			? periodOptions(manifest, selection.kind, selection.definition, selection.threshold)
			: []
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
			projection: 'Projected chance',
			projection_change: 'Change vs today'
		}[layer.kind];
	});
	const legendSubtitle = $derived.by(() => {
		if (!definition) return '';
		const period = periods.find((p) => p.value === selection.period)?.label ?? '';
		const th =
			manifest && manifest.thresholds.length > 1 && threshold
				? `${threshold.default ? 'calibrated' : 'raw'}, ≥ ${threshold.cm} cm`
				: '';
		return [period, definition.short, th].filter(Boolean).join(' · ');
	});
	const baselineLabel = $derived(
		manifest?.windows.find((w) => w.id === manifest?.projections.baseline_window)?.label ?? ''
	);
	const fixture = $derived(manifest?.data_version.includes('fixture') ?? false);
	const glaciers = $derived(manifest?.glacier_style === 'hatched');

	let lookupSeq = 0;
	async function select(lon: number, lat: number, placeLabel: PlaceLabel | null, nearestLand = 0) {
		if (!ds) return;
		dropRegion();
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

	/**
	 * places.json is the largest file the page needs (~1.3 MB gzipped for ~34k places). Fetch
	 * it once the page is idle, so the search answers right away on slow connections; the
	 * search index itself is built when the box gets focus.
	 */
	function prefetchPlaces(source: DataSource) {
		// not for Save-Data or 2G users: the search loads places on focus anyway
		const connection = (navigator as Navigator & { connection?: ConnectionLike }).connection;
		if (!allowsPrefetch(connection)) return;
		const start = () => source.places().catch(() => {});
		const idle = (cb: () => void) =>
			'requestIdleCallback' in window
				? window.requestIdleCallback(cb, { timeout: 8000 })
				: setTimeout(cb, 3000);
		setTimeout(() => idle(start), 2500);
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
		dropRegion();
		panelExpanded = false;
	}

	function dropRegion() {
		regionSeq++;
		regionId = null;
		regionCountry = null;
		regionError = null;
	}

	const message = (e: unknown) => (e instanceof Error ? e.message : String(e));
	const noSuchRegion = (id: string) => `There is no state or province “${id}” in this dataset.`;

	/** The region index (~130 kB gzipped), loaded on first use. Failures are reported, not hidden. */
	async function ensureIndex(): Promise<Admin1Index | null> {
		if (regionIndex) return regionIndex;
		if (!ds) return null;
		indexLoading = true;
		try {
			regionIndex = await ds.admin1Index();
			return regionIndex;
		} catch (e) {
			regionsNote = `The state and province data could not be loaded: ${message(e)}`;
			return null;
		} finally {
			indexLoading = false;
		}
	}

	async function setRegionsOn(on: boolean) {
		regionsOn = on;
		if (!on) return;
		regionsNote = null;
		if (!(await ensureIndex())) regionsOn = false;
	}

	let regionSeq = 0;
	/**
	 * Selects a state or province: its panel opens at once from the index row, and the
	 * country file with the statistics follows. `fly` zooms to it (search, deep link). The
	 * borders switch is left as the user set it: the region draws only its own outline.
	 */
	async function selectRegion(id: string, opts: { fly: boolean }) {
		if (!ds) return;
		const seq = ++regionSeq;
		const index = await ensureIndex();
		if (seq !== regionSeq || !index) return;
		const row = index.rows.find((r) => r.id === id);
		if (!row) {
			// a stale or mistyped link: say so rather than leave a plain map
			regionId = null;
			regionsNote = noSuchRegion(id);
			return;
		}
		try {
			RegionPanel ??= (await import('#lib/panel/RegionPanel.svelte')).default;
		} catch {
			// e.g. a stale chunk after a new deploy: nothing is selected, say so
			if (seq === regionSeq) regionsNote = 'The region panel could not be loaded. Reload the page.';
			return;
		}
		if (seq !== regionSeq) return;
		at = null;
		label = null;
		lookup = null;
		lookupError = null;
		regionId = id;
		regionCountry = null;
		regionError = null;
		regionsNote = null;
		if (opts.fly) mapView?.flyTo(row.lon, row.lat, 4);
		controlsOpen = false;
		try {
			const country = await ds.admin1Country(row.country);
			if (seq !== regionSeq) return;
			regionCountry = country;
			const bbox = country.regions.find((r) => r.id === id)?.bbox;
			// east may exceed 180 for a region across the antimeridian (Alaska): used as it is
			if (opts.fly && bbox) mapView?.fitBounds(bbox);
		} catch (e) {
			if (seq === regionSeq) regionError = message(e);
		}
	}

	function pickRegion(row: RegionRow) {
		selectRegion(row.id, { fly: true });
	}

	/**
	 * Re-checks a radio group from state. If a change was refused (normalizeSelection kept the
	 * old kind), the browser has still moved the checked mark, and Svelte won't move it back
	 * because the state didn't change.
	 */
	function syncRadios(input: HTMLInputElement, isChecked: (value: string) => boolean) {
		const group = input.form ?? input.closest('fieldset');
		group
			?.querySelectorAll<HTMLInputElement>(`input[type=radio][name="${input.name}"]`)
			.forEach((r) => (r.checked = isChecked(r.value)));
	}

	function setSelection(partial: Partial<Selection>) {
		if (!manifest) return;
		selection = normalizeSelection(manifest, { ...selection, ...partial });
	}

	// keep the URL in sync (debounced), so every view is shareable
	let urlTimer: ReturnType<typeof setTimeout> | undefined;
	$effect(() => {
		const qs = serializeUrl({
			view,
			selection,
			at: at ?? undefined,
			place: label?.name,
			regions: regionsOn,
			region: regionId ?? undefined
		});
		if (!ready) return;
		clearTimeout(urlTimer);
		urlTimer = setTimeout(() => {
			const url = `${window.location.pathname}${qs}`;
			if (url !== `${window.location.pathname}${window.location.search}${window.location.hash}`) {
				// The URL comes from window.location.pathname, which already carries the base path.
				// eslint-disable-next-line svelte/no-navigation-without-resolve
				goto(url, { replace: true, shallow: true }).catch(() => {});
			}
		}, 250);
	});

	onMount(() => {
		const url = parseUrlState(new URLSearchParams(window.location.search), window.location.hash);
		if (url.view) view = url.view;
		getDataSource()
			.then(async (source) => {
				ds = source;
				manifest = source.manifest;
				selection = normalizeSelection(source.manifest, url.selection);
				await tick();
				ready = true;
				prefetchPlaces(source);
				if (source.hasAdmin1 && url.regions) setRegionsOn(true);
				if (source.hasAdmin1 && url.regionRejected) regionsNote = noSuchRegion(url.regionRejected);
				outlinesOk = allowsPrefetch(
					(navigator as Navigator & { connection?: ConnectionLike }).connection
				);
				// a region link works on reload; a shared map view wins over zooming to the region
				if (source.hasAdmin1 && url.region) selectRegion(url.region, { fly: !url.view });
				if (url.at) {
					// Name the place only if it is a places.json entry at that spot; a link can carry
					// any text, so otherwise the panel shows the coordinates.
					let restored: PlaceLabel | null = null;
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
							/* places unavailable: show the coordinates */
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

<svelte:window
	onkeydown={(e) => {
		if (e.key === 'Escape' && hasPanel && !(e.target instanceof HTMLInputElement)) closePanel();
	}}
	onhashchange={() => {
		// someone edited the address bar: follow a region link, or close the panel when it went
		const id = parseRegionHash(window.location.hash);
		const bad = rejectedRegionHash(window.location.hash);
		if (id && id !== regionId) selectRegion(id, { fly: true });
		else if (bad) regionsNote = noSuchRegion(bad);
		else if (!id && regionId) dropRegion();
	}}
/>

<svelte:head>
	<link
		rel="preload"
		as="fetch"
		href={`${DATA_BASE}/manifest.json`}
		crossorigin="anonymous"
		fetchpriority="low"
	/>
	<link rel="preconnect" href="https://tiles.openfreemap.org" crossorigin="anonymous" />
</svelte:head>

<div class="stage" class:with-panel={hasPanel}>
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
			regions={regionsProp}
			onregionselect={(id) => selectRegion(id, { fly: false })}
			onregionsstatus={(status, detail) => {
				outlineStatus = status;
				if (status === 'error') {
					regionsNote = `The state and province borders could not be loaded${detail ? `: ${detail}` : ''}.`;
					regionsOn = false;
				}
			}}
		/>
	{/if}

	<div class="overlay-top" class:hidden-mobile={hasPanel && panelExpanded}>
		<div class="controls" class:open={controlsOpen}>
			<h1 class="intro">How likely is a white Christmas where you live?</h1>
			<div class="search-row">
				<div class="search-wrap">
					<PlaceSearch
						loadPlaces={async () => (await (await getDataSource()).places()).places}
						onpick={pickPlace}
						regionsEnabled={hasRegions}
						loadRegions={async () => (await getDataSource()).admin1Index()}
						onpickregion={pickRegion}
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
					{#if manifest.thresholds.length > 1}
						<fieldset class="kinds thresholds">
							<legend class="visually-hidden">Snow depth threshold</legend>
							{#each manifest.thresholds as t (t.id)}
								{@const usable = thresholdHasLayers(manifest, t.id, selection.definition)}
								<label
									class:checked={selection.threshold === t.id}
									class:disabled={!usable}
									title={usable ? t.label : `${t.label}: no maps for this definition`}
								>
									<input
										type="radio"
										name="threshold"
										value={t.id}
										disabled={!usable}
										checked={selection.threshold === t.id}
										onchange={(e) => {
											setSelection({ threshold: t.id });
											syncRadios(e.currentTarget, (v) => v === selection.threshold);
										}}
									/>
									{thresholdShortLabel(t)}
								</label>
							{/each}
						</fieldset>
						{#if rawUnavailable}
							<p class="level-note" data-testid="raw-note">
								Raw ERA5-Land maps exist for {rawDefinitions.join(', ') || 'another definition'} only;
								the place panel shows both values.
							</p>
						{/if}
					{/if}
					<fieldset class="kinds">
						<legend class="visually-hidden">Map layer</legend>
						{#each kinds as k (k)}
							<label class:checked={tabOf(selection.kind) === k}>
								<input
									type="radio"
									name="kind"
									value={k}
									checked={tabOf(selection.kind) === k}
									onchange={(e) => {
										setSelection({
											kind: k,
											// keep the warming level when switching between Future views
											period: isFuture(selection.kind) && isFuture(k) ? selection.period : ''
										});
										syncRadios(e.currentTarget, (v) => v === tabOf(selection.kind));
									}}
								/>
								{KIND_LABELS[k]}
							</label>
						{/each}
					</fieldset>
					{#if futureNote}
						<p class="level-note" data-testid="future-note">
							Future projections use the calibrated threshold.
						</p>
					{/if}
					{#if isFuture(selection.kind) && modes.length > 1}
						<fieldset class="kinds modes">
							<legend class="visually-hidden">Future view</legend>
							{#each modes as k (k)}
								<label class:checked={selection.kind === k}>
									<input
										type="radio"
										name="future-mode"
										value={k}
										checked={selection.kind === k}
										onchange={(e) => {
											setSelection({ kind: k, period: selection.period });
											syncRadios(e.currentTarget, (v) => v === selection.kind);
										}}
									/>
									{FUTURE_MODE_LABELS[k]}
								</label>
							{/each}
						</fieldset>
					{/if}
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
							<span>{isFuture(selection.kind) ? 'Warming' : 'Period'}</span>
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
					{#if hasRegions}
						<label class="region-toggle" class:checked={regionsOn}>
							<input
								type="checkbox"
								checked={regionsOn}
								data-testid="regions-toggle"
								onchange={(e) => setRegionsOn(e.currentTarget.checked)}
							/>
							<span>States and provinces</span>
						</label>
						{#if regionsOn}
							<p class="level-note" data-testid="regions-hint" aria-live="polite">
								{indexLoading || outlineStatus === 'loading'
									? 'Loading the borders…'
									: 'Click a state or province for its details.'}
							</p>
						{/if}
					{/if}
					{#if levelNote}
						<p class="level-note" data-testid="level-note">
							<strong>{periods.find((p) => p.value === selection.period)?.label}</strong> global
							warming: {levelNote}
						</p>
					{/if}
				</div>
			{/if}
		</div>
		{#if regionsNote}
			<p class="notice" role="status" data-testid="regions-note">
				<span>{regionsNote}</span>
				<button
					type="button"
					aria-label="Dismiss this message"
					onclick={() => (regionsNote = null)}
				>
					×
				</button>
			</p>
		{/if}
		{#if fixture}
			<p class="fixture" role="note">Fixture data: the values are fake, for development only.</p>
		{/if}
	</div>

	{#if manifest}
		<div class="overlay-legend" class:hidden-mobile={hasPanel}>
			<Legend
				{layer}
				{colormap}
				title={legendTitle}
				subtitle={legendSubtitle}
				{glaciers}
				{baselineLabel}
				{threshold}
			/>
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

	{#if manifest && regionRow && RegionPanel}
		<RegionPanel
			{manifest}
			index={regionIndex}
			row={regionRow}
			country={regionCountry}
			error={regionError}
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
	.modes {
		margin-top: 6px;
	}
	.thresholds {
		margin-bottom: 6px;
	}
	.kinds label.disabled {
		opacity: 0.45;
		cursor: not-allowed;
	}
	.level-note {
		margin: 6px 2px 0;
		font-size: 0.78rem;
		line-height: 1.35;
		color: var(--muted);
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
	.region-toggle {
		display: flex;
		align-items: center;
		gap: 8px;
		margin-top: 8px;
		padding: 6px 4px 2px;
		font-size: 0.86rem;
		cursor: pointer;
	}
	.region-toggle input {
		width: 18px;
		height: 18px;
		margin: 0;
		accent-color: var(--accent);
	}
	.notice {
		display: flex;
		align-items: flex-start;
		gap: 8px;
		margin: 8px 0 0;
		padding: 8px 10px;
		font-size: 0.85rem;
		line-height: 1.35;
		color: var(--text);
		background: var(--surface);
		border-left: 4px solid var(--warn);
		border-radius: 8px;
		box-shadow: var(--shadow);
	}
	.notice span {
		flex: 1;
		min-width: 0;
		overflow-wrap: anywhere;
	}
	.notice button {
		flex: none;
		width: 28px;
		height: 28px;
		padding: 0;
		font-size: 1.2rem;
		line-height: 1;
		color: var(--muted);
		background: transparent;
		border: 0;
		border-radius: 6px;
		cursor: pointer;
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
		/* the expanded place sheet takes the whole stage; the search card would cover it */
		.overlay-top.hidden-mobile,
		.overlay-legend.hidden-mobile {
			display: none;
		}
	}
</style>
