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
	import { formatPct, formatPp, frequencyLine, latLonLabel } from '#lib/format/format.ts';
	import {
		defaultThreshold,
		definitionText,
		thresholdById,
		thresholdNote
	} from '#lib/data/manifest.ts';
	import type { Selection } from '#lib/map/layers.ts';
	import DecadeBars from './DecadeBars.svelte';
	import PanelShell from './PanelShell.svelte';
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
	/** The selected threshold (contract v1.5); everything below is derived for it. */
	const threshold = $derived(thresholdById(manifest, selection.threshold));
	const strip = $derived(history ? yearStrip(history, definition.id, threshold.cm) : []);
	/** The headline window's probability for every threshold the data offers ("38 % · 62 %"). */
	const byThreshold = $derived(
		history && headWin && manifest.thresholds.length > 1
			? manifest.thresholds.map((t) => ({
					t,
					p: probability(yearStrip(history, definition.id, t.cm), headWin.start, headWin.end).p
				}))
			: []
	);
	const head = $derived<WindowProbability | null>(
		history && headWin ? probability(strip, headWin.start, headWin.end) : null
	);
	const decades = $derived(history ? decadeProbabilities(strip, manifest.windows) : []);
	const pThen = $derived(
		history && thenWin ? probability(strip, thenWin.start, thenWin.end) : null
	);
	const pNow = $derived(history && nowWin ? probability(strip, nowWin.start, nowWin.end) : null);
	const trend = $derived(history && full ? olsTrend(strip, full.start, full.end) : null);
	/** 'white' or 'green' when every year with data in the full period was the same. */
	const fullRun = $derived.by(() => {
		if (!full) return null;
		const states = new Set(
			strip
				.filter((c) => c.year >= full.start && c.year <= full.end && c.state !== 'nodata')
				.map((c) => c.state)
		);
		return states.size === 1 ? ([...states][0] as 'white' | 'green') : null;
	});
	const depthLabel = $derived(definition.id === 'christmas_day' ? 'on Dec 25' : 'on Dec 24–26');

	const showFuture = $derived(
		manifest.projections.available && !!lookup?.projection && lookup.projection.length > 0
	);
	const baseline = $derived.by(() => {
		if (!history || !nowWin) return null;
		// projections are for the default threshold, so the "today" value is too
		const s = yearStrip(history, 'christmas_day', defaultThreshold(manifest).cm);
		return probability(s, nowWin.start, nowWin.end).p;
	});

	const title = $derived(
		label?.name ?? (lookup ? latLonLabel(lookup.centre.lat, lookup.centre.lon) : 'Selected place')
	);
</script>

<PanelShell
	label="Place details"
	testid="place-panel"
	{title}
	subtitle={label?.detail ?? ''}
	{expanded}
	{onclose}
	{ontoggle}
>
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
			{#if head.p !== null}
				<p>
					<strong>{frequencyLine(definition.label, head.p)}</strong>
					<span class="muted">({head.nWhite} of {head.nValid} years, {headWin?.label})</span>
				</p>
				{#if byThreshold.length}
					<p class="both" data-testid="both-thresholds">
						{#each byThreshold as b, k (b.t.id)}
							{#if k > 0}<span class="sep" aria-hidden="true">·</span>{/if}
							<span class:current={b.t.id === threshold.id}>
								{formatPct(b.p)}
								{b.t.default ? 'calibrated' : 'raw ERA5-Land'}
							</span>
						{/each}
					</p>
				{/if}
			{:else}
				<p>
					Not enough years with data in {headWin?.label} ({head.nValid} of {headWin
						? headWin.end - headWin.start + 1
						: '?'}); a value needs at least 80% of the years.
				</p>
			{/if}
		</section>

		<label class="def">
			<span class="visually-hidden">Definition</span>
			<select value={definition.id} onchange={(e) => ondefinition(e.currentTarget.value)}>
				{#each manifest.definitions as d (d.id)}
					<option value={d.id}>{d.label}</option>
				{/each}
			</select>
		</label>
		<p class="muted small">
			{definitionText(manifest, definition, threshold)}
			{#if thresholdNote(manifest, threshold)}<span data-testid="threshold-note">
					{thresholdNote(manifest, threshold)}
				</span>{:else if threshold.description}<span data-testid="threshold-note">
					{threshold.description}
				</span>{/if}
		</p>

		{#if history.glacier}
			<p class="note">
				This cell is in the glacier mask: snow lies here all year, so it says little about Christmas
				weather.
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
				{#if fullRun}
					<p>
						<strong>No trend:</strong>
						{fullRun === 'white' ? 'snow on the ground' : 'no snow'} in every year with data.
					</p>
				{:else if trend.pValue < 0.1}
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
				<p class="muted small" class:hidden={!!fullRun}>
					The slope and its range come from a straight line through {trend.n} yes/no years, a rough summary;
					whether the trend is clear comes from a Mann–Kendall test (p &lt; 0.1), as on the map. Luck
					from year to year is large, so read it as a direction, not a forecast.
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
</PanelShell>
