import { useCallback, useEffect, useState } from "react";

const KEY = "doccite_sidebar_width";
const MIN = 220;
const MAX = 480;
const DEFAULT = 280;

function clamp(n: number): number {
  return Math.min(MAX, Math.max(MIN, Math.round(n)));
}

function readStored(): number {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return DEFAULT;
    const n = Number(raw);
    return Number.isFinite(n) ? clamp(n) : DEFAULT;
  } catch {
    return DEFAULT;
  }
}

export function useSidebarWidth() {
  const [width, setWidth] = useState(readStored);
  const [dragging, setDragging] = useState(false);

  useEffect(() => {
    try {
      localStorage.setItem(KEY, String(width));
    } catch {
      /* ignore */
    }
  }, [width]);

  const onResizeStart = useCallback(
    (e: { preventDefault(): void; clientX: number }) => {
      e.preventDefault();
      setDragging(true);
      const startX = e.clientX;
      const startW = width;

      const onMove = (ev: MouseEvent | PointerEvent) => {
        setWidth(clamp(startW + (ev.clientX - startX)));
      };
      const onUp = () => {
        setDragging(false);
        window.removeEventListener("pointermove", onMove);
        window.removeEventListener("pointerup", onUp);
        window.removeEventListener("mousemove", onMove);
        window.removeEventListener("mouseup", onUp);
        document.body.style.cursor = "";
        document.body.style.userSelect = "";
      };

      document.body.style.cursor = "col-resize";
      document.body.style.userSelect = "none";
      window.addEventListener("pointermove", onMove);
      window.addEventListener("pointerup", onUp);
      window.addEventListener("mousemove", onMove);
      window.addEventListener("mouseup", onUp);
    },
    [width],
  );

  return { width, dragging, onResizeStart, min: MIN, max: MAX };
}
