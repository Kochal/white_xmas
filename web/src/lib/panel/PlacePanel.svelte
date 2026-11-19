<script lang="ts">
	import {
		decadeProbabilities,
		olsTrend,
		probability,
		yearStrip,
		type WindowProbability
	} from '#lib/data/derive.ts';
	import type { Manifest, Window } from '#lib/data/manifest.ts';
	import type { CellLookup } from '#lib/data/source.ts';
	import { formatPct, formatPp, inTenYears, latLonLabel } from '#lib/format/format.ts';
	import type { Selection } from '#lib/map/layers.ts';
	import DecadeBars from './DecadeBars.svelte';
	import FutureRanges from './FutureRanges.svelte';
	import YearStrip from './YearStrip.svelte';
	import type { PlaceLabel } from './types.ts';

	interface Props {
		manifest: Manifest;
		lookup: CellLookup | null;
		loading: boolean;
		error: string | null;
		label: PlaceLabel | null;
		selection: Selection;
		expanded: boolean;
		onclose: () => void;
		ontoggle: () => void;
		ondefinition: (id: string) => void;
	}

	let {
		manifest,
		lookup,
		loading,
		error,
		label,
		selection,
		expanded,
		onclose,
		ontoggle,
		ondefinition
	}: Props = $props();

	const definition = $derived(
		manifest.definitions.find((d) => d.id === selection.definition) ?? manifest.definitions[0]
	);
	const win = (id: string | undefined): Window | undefined =>
		manifest.windows.find((w) => w.id === id);
	const full = $derived(manifest.windows.find((w) => w.kind === 'full') ?? manifest.windows[0]);
	const thenWin = $derived(win('1961_1990') ?? manifest.windows.find((w) => w.kind === 'normal'));
	const nowWin = $derived(
		win(manifest.projections.baseline_window) ??
			win('1996_2025') ??
			[...manifest.windows].filter((w) => w.kind === 'normal').sort((a, b) => b.end - a.end)[0]
	);
	/** The window of the headline: the selected period when it is a window, else the latest normal. */
	const headWin = $derived(
		(selection.kind === 'probability' || selection.kind === 'trend'
			? win(selection.period)
			: null) ??
			nowWin ??
			full
	);

	const history = $derived(lookup?.status === 'ok' ? lookup.history : null);
	const strip = $derived(history ? yearStrip(history, definition.id, manifest.threshold_cm) : []);
	const head = $derived<WindowProbability | null>(
		history && headWin ? probability(strip, headWin.start, headWin.end) : null
	);
	const decades = $derived(history ? decadeProbabilities(strip, manifest.windows) : []);
	const pThen = $derived(
		history && thenWin ? probability(strip, thenWin.start, thenWin.end) : null
	);
	const pNow = $derived(history && nowWin ? probability(strip, nowWin.start, nowWin.end) : null);
	const trend = $derived(history && full ? olsTrend(strip, full.start, full.end) : null);
	const depthLabel = $derived(definition.id === 'christmas_day' ? 'on Dec 25' : 'on Dec 24–26');

	const showFuture = $derived(
		manifest.projections.available && !!lookup?.projection && lookup.projection.length > 0
	);
	const baseline = $derived.by(() => {
		if (!history || !nowWin) return null;
		const s = yearStrip(history, 'christmas_day', manifest.threshold_cm);
		return probability(s, nowWin.start, nowWin.end).p;
	});

	const title = $derived(
		label?.name ?? (lookup ? latLonLabel(lookup.centre.lat, lookup.centre.lon) : 'Selected place')
	);
</script>

<aside class="panel" class:expanded aria-label="Place details" data-testid="place-panel">
	<header>
		<button class="grip" onclick={ontoggle} aria-expanded={expanded} aria-controls="panel-body">
			<span class="visually-hidden">{expanded ? 'Collapse' : 'Expand'} details</span>
			<span class="handle" aria-hidden="true"></span>
		</button>
		<div class="heading">
			<h2>{title}</h2>
			{#if label?.detail}<p class="muted">{label.detail}</p>{/if}
		</div>
		<button class="close" onclick={onclose} aria-label="Close details">
			<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true">
				<path d="M6 6l12 12M18 6L6 18" stroke="currentColor" stroke-width="2" />
			</svg>
		</button>
	</header>

	<div class="body" id="panel-body">
		{#if loading}
			<p class="muted" aria-live="polite">Loading the snow history…</p>
		{:else if error}
			<p role="alert">Couldn't load the data for this place: {error}</p>
		{:else if lookup && lookup.status !== 'ok'}
			<p>
				{lookup.status === 'ocean'
					? 'No data here: this grid cell is ocean, a large lake or has no snow data.'
					: 'There is no data for this location in the current dataset.'}
			</p>
		{:else if lookup && history && head}
			<section class="headline" aria-live="polite">
				<p class="big" data-testid="headline">{formatPct(head.p)}</p>
				<p>
					<strong>{definition.label}</strong> in {inTenYears(head.p)}
					<span class="muted">({head.nWhite} of {head.nValid} years, {headWin?.label})</span>
				</p>
			</section>

			<label class="def">
				<span class="visually-hidden">Definition</span>
				<select value={definition.id} onchange={(e) => ondefinition(e.currentTarget.value)}>
					{#each manifest.definitions as d (d.id)}
						<option value={d.id}>{d.label}</option>
					{/each}
				</select>
			</label>
			<p class="muted small">{definition.description}</p>

			{#if history.glacier}
				<p class="note">
					This cell is in the glacier mask: snow lies here all year, so it says little about
					Christmas weather.
				</p>
			{/if}

			<section>
				<h3>Every Christmas since {strip[0]?.year}</h3>
				<YearStrip {strip} window={headWin} {depthLabel} />
			</section>

			{#if pThen && pNow && thenWin && nowWin}
				<section>
					<h3>Then vs now</h3>
					<div class="thenNow">
						<div>
							<span class="muted">{thenWin.label}</span>
							<strong>{formatPct(pThen.p)}</strong>
						</div>
						<span class="arrow" aria-hidden="true">→</span>
						<div>
							<span class="muted">{nowWin.label}</span>
							<strong>{formatPct(pNow.p)}</strong>
						</div>
						{#if pThen.p !== null && pNow.p !== null}
							<div class="delta">{formatPp(pNow.p - pThen.p)}</div>
						{/if}
					</div>
				</section>
			{/if}

			{#if decades.length}
				<section>
					<h3>By decade</h3>
					<DecadeBars {decades} />
				</section>
			{/if}

			{#if trend}
				<section>
					<h3>Trend {full.label}</h3>
					{#if trend.pValue < 0.1}
						<p>
							<strong>{formatPp(trend.perDecade, 'pp per decade')}</strong>
							<span class="muted">
								(rough 90% range {formatPp(trend.low90, 'to')}
								{formatPp(trend.high90, 'pp')})
							</span>
						</p>
					{:else}
						<p>
							<strong>No clear trend.</strong> The fitted line ({formatPp(
								trend.perDecade,
								'pp per decade'
							)}) is within what year-to-year chance alone produces (p = {trend.pValue.toFixed(2)}).
						</p>
					{/if}
					<p class="muted small">
						A straight line through {trend.n} yes/no years is a rough summary. Luck from year to year
						is large, so read it as a direction, not a forecast.
					</p>
				</section>
			{/if}

			{#if head.meanDepthWhite !== null}
				<section>
					<h3>Snow depth</h3>
					<p>
						In white years ({headWin?.label}), snow depth {depthLabel} averaged
						<strong>{Math.round(head.meanDepthWhite)} cm</strong>.
					</p>
				</section>
			{/if}

			{#if showFuture && lookup.projection}
				<section>
					<h3>In a warmer world</h3>
					<FutureRanges
						levels={manifest.projections.warming_levels}
						values={lookup.projection}
						{baseline}
						baselineLabel={nowWin?.label ?? ''}
					/>
					<p class="muted small">
						Projections are for snow on Christmas Day, from {manifest.projections.models.length}
						climate models. The range is the spread between models (10th to 90th percentile). Models work
						on ~100 km grids, so mountains are smoothed.
					</p>
				</section>
			{/if}

			<p class="muted small fine">
				Grid cell centred at {latLonLabel(lookup.centre.lat, lookup.centre.lon)}{lookup.moved
					? ' (nearest land cell)'
					: ''}. Based on ERA5-Land reanalysis: a 9 km grid cell, not your garden.
			</p>
		{/if}
	</div>
</aside>

<style>
	.panel {
		position: absolute;
		z-index: 6;
		top: 12px;
		right: 12px;
		bottom: 12px;
		width: 380px;
		display: flex;
		flex-direction: column;
		background: var(--surface);
		border-radius: var(--radius);
		box-shadow: var(--shadow);
		overflow: hidden;
	}
	header {
		display: flex;
		align-items: flex-start;
		gap: 8px;
		padding: 14px 12px 8px 16px;
		border-bottom: 1px solid var(--line);
	}
	.heading {
		flex: 1;
		min-width: 0;
	}
	h2 {
		margin: 0;
		font-size: 1.2rem;
		line-height: 1.25;
		overflow-wrap: anywhere;
	}
	.heading p {
		margin: 2px 0 0;
		font-size: 0.88rem;
	}
	.grip {
		display: none;
	}
	.close {
		flex: none;
		padding: 4px;
		border: 0;
		border-radius: 6px;
		background: transparent;
		color: var(--muted);
		cursor: pointer;
	}
	.close:hover {
		background: var(--surface-2);
		color: var(--text);
	}
	.body {
		overflow-y: auto;
		padding: 12px 16px 16px;
		overscroll-behavior: contain;
	}
	section {
		margin: 0 0 18px;
	}
	h3 {
		margin: 0 0 6px;
		font-size: 0.82rem;
		text-transform: uppercase;
		letter-spacing: 0.04em;
		color: var(--muted);
		font-weight: 650;
	}
	.headline {
		margin-bottom: 8px;
	}
	.headline p {
		margin: 0;
	}
	.big {
		font-size: 2.6rem;
		font-weight: 700;
		line-height: 1.05;
		letter-spacing: -0.02em;
		font-variant-numeric: tabular-nums;
	}
	.def select {
		width: 100%;
		margin-top: 4px;
		padding: 6px 8px;
		font: inherit;
		font-size: 0.9rem;
		color: var(--text);
		background: var(--surface-2);
		border: 1px solid var(--line);
		border-radius: 6px;
	}
	.small {
		font-size: 0.8rem;
		line-height: 1.4;
	}
	.note {
		padding: 8px 10px;
		font-size: 0.85rem;
		background: var(--accent-soft);
		border-radius: 6px;
	}
	.thenNow {
		display: flex;
		align-items: flex-end;
		flex-wrap: wrap;
		gap: 4px 12px;
	}
	.thenNow > div {
		display: flex;
		flex-direction: column;
		font-size: 0.85rem;
	}
	.thenNow strong {
		font-size: 1.4rem;
		font-variant-numeric: tabular-nums;
	}
	.arrow {
		font-size: 1.3rem;
		color: var(--muted);
		padding-bottom: 2px;
	}
	.delta {
		margin-left: auto;
		padding: 2px 8px;
		border-radius: 999px;
		background: var(--surface-2);
		font-variant-numeric: tabular-nums;
		font-size: 0.9rem;
		align-self: center;
	}
	.fine {
		margin-top: 8px;
		padding-top: 10px;
		border-top: 1px solid var(--line);
	}

	@media (max-width: 720px) {
		.panel {
			top: auto;
			left: 0;
			right: 0;
			bottom: 0;
			width: auto;
			max-height: 42%;
			border-radius: var(--radius) var(--radius) 0 0;
			transition: max-height 0.2s ease;
		}
		.panel.expanded {
			max-height: calc(100% - 12px);
		}
		header {
			position: relative;
			padding-top: 22px;
		}
		/* touch target at least 44 px tall (WCAG 2.5.8 asks for 24) */
		.grip {
			display: block;
			position: absolute;
			z-index: 1;
			top: 0;
			left: 50%;
			transform: translateX(-50%);
			width: 120px;
			height: 44px;
			padding: 0;
			border: 0;
			background: transparent;
			cursor: pointer;
		}
		.handle {
			display: block;
			width: 40px;
			height: 4px;
			margin: 8px auto 0;
			border-radius: 2px;
			background: var(--line);
		}
	}
	@media (prefers-reduced-motion: reduce) {
		.panel {
			transition: none;
		}
	}
</style>
