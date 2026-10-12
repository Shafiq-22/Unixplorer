import type { ReactNode } from "react";
import "./globals.css";

export const metadata = {
  title: "Universe Atlas: health",
  description: "Milky Way edition. M1 health page.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
