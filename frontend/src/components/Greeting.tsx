"use client";

import { useQuery } from "@tanstack/react-query";
import { fetchMe } from "@/lib/api";

function firstName(me: { display_name: string | null; email: string }): string {
  const source = (me.display_name || me.email.split("@")[0]).trim();
  return source.split(/\s+/)[0];
}

/** A short personalized line above a page's title, e.g. "Hello Rahat, here is your analytics." */
export function Greeting({ text }: { text: (name: string) => string }) {
  const { data: me } = useQuery({ queryKey: ["me"], queryFn: fetchMe });
  if (!me) return null;
  return <p className="text-sm font-medium text-accent-text mb-1">{text(firstName(me))}</p>;
}
