import type { Metadata } from "next";
import { Suspense } from "react";
import EclassFeedPage from "@/components/pages/EclassFeedPage";

export const metadata: Metadata = { title: "E클래스 공지·자료 · 유니버스" };

export default function Page() {
  return (
    <Suspense>
      <EclassFeedPage />
    </Suspense>
  );
}
