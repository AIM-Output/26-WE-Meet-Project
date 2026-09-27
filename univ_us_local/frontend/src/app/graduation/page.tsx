import type { Metadata } from "next";
import { Suspense } from "react";
import GraduationPage from "@/components/pages/GraduationPage";

export const metadata: Metadata = { title: "졸업요건 · 유니버스" };

export default function Page() {
  return (
    <Suspense>
      <GraduationPage />
    </Suspense>
  );
}
