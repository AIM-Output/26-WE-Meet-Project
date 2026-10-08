import type { Metadata } from "next";
import { Suspense } from "react";
import ExamsPage from "@/components/pages/ExamsPage";

export const metadata: Metadata = { title: "시험·발표 · 유니버스" };

export default function Page() {
  return (
    <Suspense>
      <ExamsPage />
    </Suspense>
  );
}
