import type { Metadata, Viewport } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Speaking Coach — practice speaking, not just studying",
  description:
    "A calm conversation studio for spoken-language practice. A live voice call in the browser, honest audio-grounded feedback, and nothing kept unless you ask.",
  applicationName: "Speaking Coach",
  appleWebApp: {
    capable: true,
    title: "Speaking Coach",
    statusBarStyle: "default",
  },
};

/**
 * The phone viewport.
 *
 * `viewportFit: "cover"` lets the page paint under the notch and the home
 * indicator; the layout then keeps controls clear of those areas with
 * `env(safe-area-inset-*)` in `globals.css` and `app.module.css`.
 * `themeColor` matches the brand green in the manifest so the browser
 * chrome blends with the header.
 *
 * Source: Next.js `generateViewport` / `viewport` reference
 * (<https://nextjs.org/docs/app/api-reference/functions/generate-viewport>,
 * checked 2026-11-07), MDN viewport meta tag
 * (<https://developer.mozilla.org/en-US/docs/Web/HTML/Viewport_meta_tag>,
 * checked 2026-11-07).
 */
export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  themeColor: "#10655a",
  colorScheme: "light",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
