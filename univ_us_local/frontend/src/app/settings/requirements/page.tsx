import type { Metadata } from "next";
import { Suspense } from "react";
import { RequirementsSettings } from "@/components/pages/SettingsPages";

export const metadata: Metadata = { title: "졸업요건 기준 · 유니버스" };

export default function Page() {
  return (
    <Suspense>
      <RequirementsSettings />
    </Suspense>
  );
}
