import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Speaking Coach — practice speaking, not just studying",
  description:
    "A calm conversation studio for spoken-language practice. Foundation build: live calling is not implemented yet, no microphone access, nothing stored.",
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
