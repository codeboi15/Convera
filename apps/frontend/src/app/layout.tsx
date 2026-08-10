import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "InterCom",
  description: "Customer communication platform — live chat, email, and knowledge base.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
