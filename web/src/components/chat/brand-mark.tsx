/** Brightpan mark: a skillet seen from above, long handle to the right. */
export function BrandMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 44 28" className={className} aria-hidden fill="none">
      <circle cx="13" cy="14" r="12" fill="currentColor" />
      <circle cx="13" cy="14" r="7.5" stroke="white" strokeOpacity="0.4" strokeWidth="1.5" />
      <rect x="23" y="11.5" width="20" height="5" rx="2.5" fill="currentColor" />
      <circle cx="39.5" cy="14" r="1.2" fill="white" />
    </svg>
  );
}
