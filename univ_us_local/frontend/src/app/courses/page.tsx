import type { Metadata } from "next";
import { Suspense } from "react";
import CoursesPage from "@/components/pages/CoursesPage";

export const metadata: Metadata = { title: "강의자료 · 유니버스" };

export default function Page() {
  return (
    <Suspense>
      <CoursesPage />
    </Suspense>
  );
}
