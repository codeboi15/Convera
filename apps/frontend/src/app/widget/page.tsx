import { Suspense } from "react";
import WidgetChat from "./WidgetChat";

export const dynamic = "force-dynamic";

export default function WidgetPage() {
  return (
    <Suspense fallback={<div className="p-4 text-sm text-neutral-500">Loading…</div>}>
      <WidgetChat />
    </Suspense>
  );
}
