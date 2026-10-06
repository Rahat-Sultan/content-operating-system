"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";

/**
 * Horizontal scroller for wide content such as tables. Shows a thin visible scrollbar,
 * fades the edge that has more content, and hints "swipe" on small screens.
 */
export function ScrollX({ children, className = "" }: { children: ReactNode; className?: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const [canLeft, setCanLeft] = useState(false);
  const [canRight, setCanRight] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const update = () => {
      setCanLeft(el.scrollLeft > 4);
      setCanRight(el.scrollLeft + el.clientWidth < el.scrollWidth - 4);
    };
    update();
    const observer = new ResizeObserver(update);
    observer.observe(el);
    window.addEventListener("resize", update);
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", update);
    };
  }, []);

  return (
    <div className="relative">
      <div
        ref={ref}
        onScroll={() => {
          const el = ref.current;
          if (!el) return;
          setCanLeft(el.scrollLeft > 4);
          setCanRight(el.scrollLeft + el.clientWidth < el.scrollWidth - 4);
        }}
        className={`cos-scroll-x overflow-x-auto ${className}`}
      >
        {children}
      </div>
      {canLeft && (
        <div aria-hidden className="pointer-events-none absolute inset-y-0 left-0 w-6 rounded-l-lg bg-gradient-to-r from-canvas to-transparent" />
      )}
      {canRight && (
        <div aria-hidden className="pointer-events-none absolute inset-y-0 right-0 w-10 rounded-r-lg bg-gradient-to-l from-canvas to-transparent" />
      )}
      {canRight && (
        <p className="mt-2 flex items-center justify-end gap-1 text-[11px] text-subtle md:hidden">
          Swipe left to see more
          <span aria-hidden>→</span>
        </p>
      )}
    </div>
  );
}
