import type { Metadata, Viewport } from "next";
import { Plus_Jakarta_Sans } from "next/font/google";
import "pretendard/dist/web/variable/pretendardvariable.css";
import "./globals.css";
import Providers from "@/components/app/Providers";

// 본문·한글: Pretendard (로컬 번들 — 오프라인에서도 같은 글꼴) · 숫자·영문 표시: Plus Jakarta Sans (ui-ux-pro-max 추천 페어링)
const jakarta = Plus_Jakarta_Sans({ subsets: ["latin"], weight: ["500", "600", "700", "800"], variable: "--font-jakarta", display: "swap" });

export const metadata: Metadata = {
  title: "유니버스 Univ-Us",
  description: "대학생 학사·일정 개인 비서 — 로컬 대시보드",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#0f766e",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="ko" className={jakarta.variable}>
      <body>
        <a
          href="#main"
          className="sr-only z-[80] rounded-lg bg-primary px-4 py-2 font-semibold text-white focus:not-sr-only focus:fixed focus:top-3 focus:left-3"
        >
          본문으로 건너뛰기
        </a>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
