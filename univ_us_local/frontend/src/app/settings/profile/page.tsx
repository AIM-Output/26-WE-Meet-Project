import type { Metadata } from "next";
import { Suspense } from "react";
import { ProfileSettings } from "@/components/pages/SettingsPages";

export const metadata: Metadata = { title: "내 프로필 · 유니버스" };

export default function Page() {
  return (
    <Suspense>
      <ProfileSettings />
    </Suspense>
  );
}
