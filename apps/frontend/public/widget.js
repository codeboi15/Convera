/**
 * InterCom embeddable chat widget loader.
 *
 * Install on any site with a single tag:
 *   <script src="https://<app>/widget.js" data-workspace="acme-support" async></script>
 *
 * The loader stays deliberately tiny: it injects a launcher button and an
 * iframe. Rendering the chat inside an iframe isolates it from the host page's
 * CSS and JavaScript, so the widget cannot be styled, scraped, or tampered
 * with by the surrounding page.
 */
(function () {
  "use strict";

  if (window.__intercomWidgetLoaded) return;
  window.__intercomWidgetLoaded = true;

  var script =
    document.currentScript ||
    (function () {
      var all = document.getElementsByTagName("script");
      return all[all.length - 1];
    })();

  var workspace = script.getAttribute("data-workspace");
  if (!workspace) {
    console.error("[InterCom] Missing data-workspace attribute on script tag.");
    return;
  }

  var origin = new URL(script.src, window.location.href).origin;
  var accent = script.getAttribute("data-accent") || "#4f46e5";
  var position = script.getAttribute("data-position") === "left" ? "left" : "right";

  var OPEN_W = 384;
  var OPEN_H = 600;

  // ── Launcher button ──────────────────────────────────────────────────────
  var launcher = document.createElement("button");
  launcher.type = "button";
  launcher.setAttribute("aria-label", "Open chat");
  launcher.style.cssText = [
    "position:fixed",
    "bottom:20px",
    position + ":20px",
    "width:56px",
    "height:56px",
    "border-radius:50%",
    "border:none",
    "cursor:pointer",
    "background:" + accent,
    "box-shadow:0 4px 16px rgba(0,0,0,.24)",
    "z-index:2147483646",
    "display:flex",
    "align-items:center",
    "justify-content:center",
    "transition:transform .18s ease",
    "padding:0",
  ].join(";");

  var ICON_CHAT =
    '<svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"/></svg>';
  var ICON_CLOSE =
    '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.5" stroke-linecap="round"><path d="M18 6 6 18M6 6l12 12"/></svg>';
  launcher.innerHTML = ICON_CHAT;

  // Unread badge driven by messages posted from the iframe.
  var badge = document.createElement("span");
  badge.style.cssText = [
    "position:absolute",
    "top:-2px",
    "right:-2px",
    "min-width:20px",
    "height:20px",
    "border-radius:10px",
    "background:#dc2626",
    "color:#fff",
    "font:600 11px/20px -apple-system,BlinkMacSystemFont,sans-serif",
    "text-align:center",
    "display:none",
    "padding:0 5px",
    "box-sizing:border-box",
  ].join(";");
  launcher.appendChild(badge);

  // ── Chat frame ───────────────────────────────────────────────────────────
  var frame = document.createElement("iframe");
  frame.title = "Chat";
  frame.src =
    origin + "/widget?workspace=" + encodeURIComponent(workspace) +
    "&accent=" + encodeURIComponent(accent);
  frame.style.cssText = [
    "position:fixed",
    "bottom:88px",
    position + ":20px",
    "width:" + OPEN_W + "px",
    "height:" + OPEN_H + "px",
    "max-height:calc(100vh - 112px)",
    "max-width:calc(100vw - 40px)",
    "border:none",
    "border-radius:16px",
    "box-shadow:0 12px 48px rgba(0,0,0,.24)",
    "z-index:2147483645",
    "display:none",
    "background:#fff",
  ].join(";");

  var open = false;

  function setOpen(next) {
    open = next;
    frame.style.display = open ? "block" : "none";
    launcher.innerHTML = open ? ICON_CLOSE : ICON_CHAT;
    launcher.appendChild(badge);
    launcher.setAttribute("aria-label", open ? "Close chat" : "Open chat");
    if (open) {
      badge.style.display = "none";
      // Let the embedded app know it is visible so it can focus the input.
      try {
        frame.contentWindow.postMessage({ type: "intercom:opened" }, origin);
      } catch (e) {
        /* cross-origin timing — safe to ignore */
      }
    }
  }

  launcher.addEventListener("click", function () {
    setOpen(!open);
  });
  launcher.addEventListener("mouseenter", function () {
    launcher.style.transform = "scale(1.06)";
  });
  launcher.addEventListener("mouseleave", function () {
    launcher.style.transform = "scale(1)";
  });

  // Messages from the iframe (same-origin app) drive host-page chrome.
  window.addEventListener("message", function (event) {
    if (event.origin !== origin || !event.data) return;
    var data = event.data;
    if (data.type === "intercom:unread") {
      var n = Number(data.count) || 0;
      badge.textContent = n > 9 ? "9+" : String(n);
      badge.style.display = n > 0 && !open ? "block" : "none";
    } else if (data.type === "intercom:close") {
      setOpen(false);
    }
  });

  function mount() {
    document.body.appendChild(frame);
    document.body.appendChild(launcher);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", mount);
  } else {
    mount();
  }

  // Minimal public API for host pages.
  window.InterCom = {
    open: function () {
      setOpen(true);
    },
    close: function () {
      setOpen(false);
    },
    toggle: function () {
      setOpen(!open);
    },
  };
})();
