import type { NextConfig } from "next";

// `next dev`  : /api 를 FastAPI(127.0.0.1:8000) 로 넘긴다 (rewrites).
// `next build`: 정적 export → frontend/out. FastAPI 가 같은 origin 에서 서빙하므로 rewrites 가 필요 없다.
//               trailingSlash 로 out/academic/index.html 처럼 폴더마다 index.html 을 만든다 —
//               StaticFiles(html=True) 가 /academic 을 주소창에 직접 쳐도 열 수 있게 (Frontend-Route 1절).
const isExport =
  process.env.NEXT_OUTPUT !== undefined ? process.env.NEXT_OUTPUT === "export" : process.env.NODE_ENV === "production";
const backend = process.env.BACKEND_URL ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = isExport
  ? { output: "export", trailingSlash: true }
  : {
      async rewrites() {
        return [{ source: "/api/:path*", destination: `${backend}/api/:path*` }];
      },
    };

export default nextConfig;
