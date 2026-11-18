import type { CSSProperties } from "react";
import { hueFor, initials } from "../lib/initials";

/** Decorative: the name is always printed next to it, so screen readers skip it. */
export function Avatar({ name }: { name: string }) {
  return (
    <span className="avatar" aria-hidden="true" style={{ "--hue": hueFor(name) } as CSSProperties}>
      {initials(name)}
    </span>
  );
}
