import type { Metadata } from "next";
import { Suspense } from "react";
import TeamPage from "@/components/pages/TeamPage";

export const metadata: Metadata = { title: "팀플 · 유니버스" };

export default function Page() {
  return (
    <Suspense>
      <TeamPage />
    </Suspense>
  );
}
