"use client";

import dynamic from "next/dynamic";

const ControlRoom = dynamic(
  () => import("@/components/control-room").then((module) => module.ControlRoom),
  {
    ssr: false,
    loading: () => (
      <main className="grid min-h-screen place-items-center text-sm text-slate-400">
        Opening the trade control room…
      </main>
    ),
  },
);

export function ControlRoomLoader() {
  return <ControlRoom />;
}
