import { CallExperience } from "@/features/call";
import catalog from "@gnani/contracts/data/catalog.json";

/**
 * The single page of the app.
 *
 * The frozen mount point: `page.tsx` renders the `CallExperience`
 * feature and passes the shared catalog to it. It owns no state and no
 * markup of its own, so Phase 04 can build the real call UI inside the
 * feature without touching this file.
 */
export default function HomePage() {
  return <CallExperience catalog={catalog} />;
}
