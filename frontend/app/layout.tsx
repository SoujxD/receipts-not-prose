import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Interest Form Assistant",
  description: "Chat with an assistant that saves, updates and deletes interest forms, with receipts for every saved change.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className={`${inter.className} bg-neutral-100 text-neutral-900`}>{children}</body>
    </html>
  );
}
