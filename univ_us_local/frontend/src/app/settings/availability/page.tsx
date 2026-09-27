import type { Metadata } from "next";
import { Suspense } from "react";
import { AvailabilitySettings } from "@/components/pages/SettingsPages";

export const metadata: Metadata = { title: "가용 시간 · 유니버스" };

export default function Page() {
  return (
    <Suspense>
      <AvailabilitySettings />
    </Suspense>
  );
}
