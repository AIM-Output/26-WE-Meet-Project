import type { Metadata } from "next";
import { Suspense } from "react";
import ChatPage from "@/components/pages/ChatPage";

export const metadata: Metadata = { title: "대화 · 유니버스" };

export default function Page() {
  return (
    <Suspense>
      <ChatPage />
    </Suspense>
  );
}
