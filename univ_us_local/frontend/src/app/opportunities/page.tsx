import type { Metadata } from "next";
import { Suspense } from "react";
import OpportunitiesPage from "@/components/pages/OpportunitiesPage";

export const metadata: Metadata = { title: "기회 · 유니버스" };

export default function Page() {
  return (
    <Suspense>
      <OpportunitiesPage />
    </Suspense>
  );
}
