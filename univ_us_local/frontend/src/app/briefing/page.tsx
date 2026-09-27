import type { Metadata } from "next";
import { Suspense } from "react";
import BriefingPage from "@/components/pages/BriefingPage";

export const metadata: Metadata = { title: "브리핑 · 유니버스" };

export default function Page() {
  return (
    <Suspense>
      <BriefingPage />
    </Suspense>
  );
}
