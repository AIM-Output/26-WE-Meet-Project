import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "유니버스 Univ-Us",
  description: "대학생 학사·일정 개인 비서 — 로컬 대시보드",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="ko">
      <body>{children}</body>
    </html>
  );
}
