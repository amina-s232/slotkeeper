/** "Dr Rao" -> "DR", "Sam" -> "S", "  " -> "?". Used for the avatar circles. */
export function initials(name: string): string {
  const words = name.trim().split(/\s+/).filter(Boolean);
  if (words.length === 0) return "?";
  return words
    .slice(0, 2)
    .map((w) => Array.from(w)[0]!.toUpperCase())
    .join("");
}

/** The same name always gets the same hue (0-359), so a provider keeps their colour. */
export function hueFor(name: string): number {
  let hash = 0;
  for (const ch of name) hash = (hash * 31 + ch.codePointAt(0)!) % 360;
  return hash;
}
