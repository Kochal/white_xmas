<script lang="ts">
	import '../app.css';
	import favicon from '#lib/assets/favicon.svg';
	import SiteHeader from '#lib/components/SiteHeader.svelte';
	import type { LayoutProps } from './$types';

	let { children }: LayoutProps = $props();
</script>

<svelte:head>
	<link rel="icon" href={favicon} type="image/svg+xml" />
</svelte:head>

<a class="skip-link" href="#main">Skip to content</a>
<SiteHeader />
<main id="main">
	{@render children()}
</main>

<style>
	.skip-link {
		position: absolute;
		left: 8px;
		top: -40px;
		z-index: 100;
		padding: 8px 12px;
		background: var(--surface);
		border-radius: 6px;
	}
	.skip-link:focus {
		top: 8px;
	}
</style>
