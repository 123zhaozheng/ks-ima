/**
 * Shared types for the folder picker. Kept outside the SFC because typed
 * linting cannot resolve type exports from `.vue` modules.
 */
export type PickedFolder = { id: string, title: string }
