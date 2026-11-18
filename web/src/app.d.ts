// See https://svelte.dev/docs/kit/types#app.d.ts
// for information about these interfaces
declare global {
	namespace App {
		// interface Error {}
		// interface Locals {}
		// interface PageData {}
		// interface PageState {}
		// interface Platform {}
	}
	/** Injected by vite.config.ts: the configured `paths.base`. */
	const __BASE_PATH__: string;
}

export {};
