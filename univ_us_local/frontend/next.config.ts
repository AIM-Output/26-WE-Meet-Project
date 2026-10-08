import type { NextConfig } from "next";

// `next dev`  : /api 를 FastAPI 로 넘긴다 (rewrites). 기본은 데스크톱 개발 모드 사이드카(127.0.0.1:8020, desktop/README.md).
//               /desktop/launch 도 넘겨서 앱 창의 세션 쿠키가 next dev 주소(127.0.0.1:3000)에 붙게 한다.
// `next build`: 정적 export → frontend/out. FastAPI 가 같은 origin 에서 서빙하므로 rewrites 가 필요 없다.
//               trailingSlash 로 out/academic/index.html 처럼 폴더마다 index.html 을 만든다 —
//               StaticFiles(html=True) 가 /academic 을 주소창에 직접 쳐도 열 수 있게 (Frontend-Route 1절).
const isExport =
  process.env.NEXT_OUTPUT !== undefined ? process.env.NEXT_OUTPUT === "export" : process.env.NODE_ENV === "production";
const backend = process.env.BACKEND_URL ?? "http://127.0.0.1:8020";

const nextConfig: NextConfig = isExport
  ? { output: "export", trailingSlash: true }
  : {
      async rewrites() {
        return [
          { source: "/api/:path*", destination: `${backend}/api/:path*` },
          { source: "/desktop/:path*", destination: `${backend}/desktop/:path*` },
          // 공부 캘린더는 F5_Test_agent/web 의 페이지를 백엔드가 준다 (2026-10-01)
          { source: "/study-calendar", destination: `${backend}/study-calendar` },
        ];
      },
    };

export default nextConfig;
