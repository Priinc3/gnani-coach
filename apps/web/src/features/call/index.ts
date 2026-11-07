/**
 * The call experience entry point — **Phase 04 owns this tree**.
 *
 * The frozen seam is this exact path:
 *
 * - `apps/web/src/features/call/index.ts` exports `CallExperience`;
 * - `CallExperience` is a React component whose only prop is
 *   `{ catalog }`;
 * - `apps/web/src/app/page.tsx` renders it and nothing else.
 *
 * The component itself lives in `CallExperience.tsx` next to this file
 * because it contains JSX, and a `.ts` file cannot hold JSX. The export
 * name and the path are the frozen part.
 */
export { CallExperience, default } from "./CallExperience";
export type { CallCatalog, CallExperienceProps } from "./CallExperience";
