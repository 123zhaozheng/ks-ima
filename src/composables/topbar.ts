import { ref } from 'vue'

/*
 * Unified TopBar state: a page may replace the route-meta title with a live
 * value (e.g. the open conversation's subject) and teleport its own title
 * node into `#topbar-title`. Empty string = show the default title; the page
 * clears the override when it unmounts.
 */
export const topbarTitleOverride = ref('')
