<script lang="ts">
	import type { Snippet } from 'svelte';

	interface Props {
		/** Accessible name of the panel ("Place details"). */
		label: string;
		testid: string;
		title: string;
		subtitle?: string;
		expanded: boolean;
		onclose: () => void;
		ontoggle: () => void;
		children: Snippet;
	}

	let {
		label,
		testid,
		title,
		subtitle = '',
		expanded,
		onclose,
		ontoggle,
		children
	}: Props = $props();
</script>

<aside class="panel" class:expanded aria-label={label} data-testid={testid}>
	<header>
		<button class="grip" onclick={ontoggle} aria-expanded={expanded} aria-controls="panel-body">
			<span class="visually-hidden">{expanded ? 'Collapse' : 'Expand'} details</span>
			<span class="handle" aria-hidden="true"></span>
		</button>
		<div class="heading">
			<h2>{title}</h2>
			{#if subtitle}<p class="muted">{subtitle}</p>{/if}
		</div>
		<button class="close" onclick={onclose} aria-label="Close details">
			<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true">
				<path d="M6 6l12 12M18 6L6 18" stroke="currentColor" stroke-width="2" />
			</svg>
		</button>
	</header>

	<div class="body" id="panel-body">
		{@render children()}
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

	/* The content blocks both panels use (the place panel and the region panel). */
	.body :global(section) {
		margin: 0 0 18px;
	}
	.body :global(h3) {
		margin: 0 0 6px;
		font-size: 0.82rem;
		text-transform: uppercase;
		letter-spacing: 0.04em;
		color: var(--muted);
		font-weight: 650;
	}
	.body :global(.headline) {
		margin-bottom: 8px;
	}
	.body :global(.headline p) {
		margin: 0;
	}
	.body :global(.big) {
		font-size: 2.6rem;
		font-weight: 700;
		line-height: 1.05;
		letter-spacing: -0.02em;
		font-variant-numeric: tabular-nums;
	}
	.body :global(.def select) {
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
	.body :global(.both) {
		margin-top: 4px !important;
		font-size: 0.88rem;
		color: var(--muted);
		font-variant-numeric: tabular-nums;
	}
	.body :global(.both .sep) {
		margin: 0 0.4em;
	}
	.body :global(.both .current) {
		color: var(--text);
		font-weight: 600;
	}
	.body :global(.small) {
		font-size: 0.8rem;
		line-height: 1.4;
	}
	.body :global(.note) {
		padding: 8px 10px;
		font-size: 0.85rem;
		background: var(--accent-soft);
		border-radius: 6px;
	}
	.body :global(.thenNow) {
		display: flex;
		align-items: flex-end;
		flex-wrap: wrap;
		gap: 4px 12px;
	}
	.body :global(.thenNow > div) {
		display: flex;
		flex-direction: column;
		font-size: 0.85rem;
	}
	.body :global(.thenNow strong) {
		font-size: 1.4rem;
		font-variant-numeric: tabular-nums;
	}
	.body :global(.arrow) {
		font-size: 1.3rem;
		color: var(--muted);
		padding-bottom: 2px;
	}
	.body :global(.delta) {
		margin-left: auto;
		padding: 2px 8px;
		border-radius: 999px;
		background: var(--surface-2);
		font-variant-numeric: tabular-nums;
		font-size: 0.9rem;
		align-self: center;
	}
	.body :global(.hidden) {
		display: none;
	}
	.body :global(.fine) {
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
