"use client";

import type { ReactNode } from "react";

// 주간 격자 — 배치 미리보기(F8)·팀 히트맵(F16)이 같이 쓴다(Frontend-Screens 4-2 "격자는 한 번만").
// 표로 그려 스크린리더가 요일·시간을 읽을 수 있게 한다.

export function WeekGrid({
  days,
  hours,
  renderCell,
  caption,
  cellHeight = 36,
}: {
  days: readonly string[];
  hours: readonly number[];
  renderCell: (day: number, hour: number) => ReactNode;
  caption: string;
  cellHeight?: number;
}) {
  return (
    <div className="thin-scroll overflow-x-auto">
      <table className="w-full min-w-[480px] border-separate border-spacing-1 text-[12px]">
        <caption className="sr-only">{caption}</caption>
        <thead>
          <tr>
            <th scope="col" className="w-12" />
            {days.map((d) => (
              <th key={d} scope="col" className="pb-1 text-[13px] font-semibold text-muted">
                {d}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {hours.map((h) => (
            <tr key={h}>
              <th scope="row" className="num pr-1 text-right align-top text-[12px] font-medium text-faint">
                {String(h).padStart(2, "0")}
              </th>
              {days.map((_, di) => (
                <td key={di} className="p-0 align-top" style={{ height: cellHeight }}>
                  {renderCell(di, h)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
