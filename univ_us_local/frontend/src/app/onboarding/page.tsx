import type { Metadata } from "next";
import { Suspense } from "react";
import OnboardingPage from "@/components/pages/OnboardingPage";

export const metadata: Metadata = { title: "첫 설정 · 유니버스" };

export default function Page() {
  return (
    <Suspense>
      <OnboardingPage />
    </Suspense>
  );
}
