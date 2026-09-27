import type { Metadata } from "next";
import { Suspense } from "react";
import AssignmentsPage from "@/components/pages/AssignmentsPage";

export const metadata: Metadata = { title: "과제·마감 · 유니버스" };

export default function Page() {
  return (
    <Suspense>
      <AssignmentsPage />
    </Suspense>
  );
}
