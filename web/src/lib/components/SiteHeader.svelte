<script lang="ts">
	import { resolve } from '$app/paths';
	import { page } from '$app/state';

	const links = [
		{ href: resolve('/'), label: 'Map' },
		{ href: resolve('/rankings'), label: 'Rankings' },
		{ href: resolve('/methodology'), label: 'Methodology' },
		{ href: resolve('/downloads'), label: 'Downloads' },
		{ href: resolve('/about'), label: 'About' }
	];

	let open = $state(false);
	const strip = (p: string) => p.replace(/\/$/, '');
	const current = (href: string) => strip(page.url.pathname) === strip(href);
</script>

<header class="site-header">
	<a class="brand" href={resolve('/')}>
		<svg viewBox="0 0 64 64" aria-hidden="true" width="22" height="22">
			<g stroke="currentColor" stroke-width="5" stroke-linecap="round" fill="none">
				<path d="M32 8v48M11.2 20l41.6 24M11.2 44l41.6-24" />
			</g>
		</svg>
		<span>White Christmas</span>
	</a>
	<button
		class="menu-button"
		aria-expanded={open}
		aria-controls="site-nav"
		onclick={() => (open = !open)}
	>
		<span class="visually-hidden">Menu</span>
		<svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true">
			<path d="M3 6h18M3 12h18M3 18h18" stroke="currentColor" stroke-width="2" />
		</svg>
	</button>
	<nav id="site-nav" class:open aria-label="Main">
		{#each links as link (link.href)}
			<a
				href={link.href}
				aria-current={current(link.href) ? 'page' : undefined}
				onclick={() => (open = false)}
			>
				{link.label}
			</a>
		{/each}
	</nav>
</header>

<style>
	.site-header {
		position: relative;
		z-index: 20;
		display: flex;
		align-items: center;
		gap: 12px;
		height: var(--header-h);
		padding: 0 16px;
		background: var(--surface);
		border-bottom: 1px solid var(--line);
	}
	.brand {
		display: inline-flex;
		align-items: center;
		gap: 8px;
		font-weight: 650;
		letter-spacing: 0.01em;
		color: var(--text);
		text-decoration: none;
		white-space: nowrap;
	}
	.brand svg {
		color: var(--accent);
	}
	nav {
		display: flex;
		gap: 4px;
		margin-left: auto;
	}
	nav a {
		padding: 6px 10px;
		border-radius: 6px;
		color: var(--muted);
		text-decoration: none;
		font-size: 0.95rem;
	}
	nav a:hover {
		color: var(--text);
		background: var(--surface-2);
	}
	nav a[aria-current='page'] {
		color: var(--text);
		background: var(--accent-soft);
	}
	.menu-button {
		display: none;
		margin-left: auto;
		padding: 6px;
		border: 0;
		border-radius: 6px;
		background: transparent;
		color: var(--text);
		cursor: pointer;
	}
	@media (max-width: 720px) {
		.menu-button {
			display: inline-flex;
		}
		nav {
			display: none;
			position: absolute;
			top: var(--header-h);
			right: 8px;
			flex-direction: column;
			min-width: 180px;
			padding: 6px;
			background: var(--surface);
			border: 1px solid var(--line);
			border-radius: var(--radius);
			box-shadow: var(--shadow);
		}
		nav.open {
			display: flex;
		}
		nav a {
			padding: 10px 12px;
		}
	}
</style>
