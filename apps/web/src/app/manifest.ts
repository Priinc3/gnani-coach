import type { MetadataRoute } from "next";

/**
 * The installable web app manifest.
 *
 * This is a Next.js metadata route: `app/manifest.ts` is served at
 * `/manifest.webmanifest` and Next adds the `<link rel="manifest">` tag
 * itself.
 *
 * There is deliberately **no service worker**. A cache in front of this
 * app could replay a signed-in learner's history or recordings to the next
 * person on the device, so offline caching is out of scope for this build.
 *
 * Source: Next.js manifest file convention
 * (<https://nextjs.org/docs/app/api-reference/file-conventions/metadata/manifest>,
 * checked 2026-11-07) and MDN Web App Manifest
 * (<https://developer.mozilla.org/en-US/docs/Web/Manifest>, checked
 * 2026-11-07).
 */
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "Speaking Coach — practice speaking out loud",
    short_name: "Speaking Coach",
    description:
      "Practise a real conversation out loud with a live voice coach, then see what was measured in your own audio.",
    id: "/",
    start_url: "/",
    scope: "/",
    display: "standalone",
    orientation: "portrait-primary",
    background_color: "#f7f6f2",
    theme_color: "#10655a",
    icons: [
      {
        src: "/icons/icon-192.png",
        sizes: "192x192",
        type: "image/png",
        purpose: "any",
      },
      {
        src: "/icons/icon-512.png",
        sizes: "512x512",
        type: "image/png",
        purpose: "any",
      },
      {
        src: "/icons/icon-maskable-512.png",
        sizes: "512x512",
        type: "image/png",
        purpose: "maskable",
      },
    ],
  };
}
