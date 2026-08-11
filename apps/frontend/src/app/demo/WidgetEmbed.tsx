"use client";

import { useEffect } from "react";

/**
 * Injects the widget loader the same way a third-party site would. Kept in a
 * client component so the demo page mirrors a real installation instead of
 * importing the chat UI directly.
 */
export default function WidgetEmbed({ workspace }: { workspace: string }) {
  useEffect(() => {
    if (document.getElementById("intercom-widget-script")) return;

    const script = document.createElement("script");
    script.id = "intercom-widget-script";
    script.src = "/widget.js";
    script.async = true;
    script.setAttribute("data-workspace", workspace);
    document.body.appendChild(script);
  }, [workspace]);

  return null;
}
