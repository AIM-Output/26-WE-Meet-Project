import type { Metadata } from "next";
import { Suspense } from "react";
import ScholarshipsPage from "@/components/pages/ScholarshipsPage";

export const metadata: Metadata = { title: "장학 · 유니버스" };

export default function Page() {
  return (
    <Suspense>
      <ScholarshipsPage />
    </Suspense>
  );
}
