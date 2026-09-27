import type { Metadata } from "next";
import { Suspense } from "react";
import AcademicPage from "@/components/pages/AcademicPage";

export const metadata: Metadata = { title: "학사일정 · 유니버스" };

export default function Page() {
  return (
    <Suspense>
      <AcademicPage />
    </Suspense>
  );
}
