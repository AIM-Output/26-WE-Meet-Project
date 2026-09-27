import type { Metadata } from "next";
import { Suspense } from "react";
import { NotificationSettings } from "@/components/pages/SettingsPages";

export const metadata: Metadata = { title: "알림·브리핑 · 유니버스" };

export default function Page() {
  return (
    <Suspense>
      <NotificationSettings />
    </Suspense>
  );
}
