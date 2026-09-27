import { Suspense } from "react";
import Dashboard from "@/components/dashboard/Dashboard";

// 쿼리 파라미터(useSearchParams)를 읽는 화면은 Suspense 안에서 클라이언트 렌더링한다(정적 export).
export default function Home() {
  return (
    <Suspense>
      <Dashboard />
    </Suspense>
  );
}
