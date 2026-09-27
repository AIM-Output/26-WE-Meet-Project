import type { Metadata } from "next";
import { Suspense } from "react";
import { SourcesSettings } from "@/components/pages/SettingsPages";

export const metadata: Metadata = { title: "수집 원천 · 유니버스" };

export default function Page() {
  return (
    <Suspense>
      <SourcesSettings />
    </Suspense>
  );
}
