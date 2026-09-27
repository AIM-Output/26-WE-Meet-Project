import type { Metadata } from "next";
import { Suspense } from "react";
import AttendancePage from "@/components/pages/AttendancePage";

export const metadata: Metadata = { title: "출결 · 유니버스" };

export default function Page() {
  return (
    <Suspense>
      <AttendancePage />
    </Suspense>
  );
}
