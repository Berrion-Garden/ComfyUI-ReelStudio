import { useEffect, useState } from "react";

/** An <img> that owns its failure: a file that won't load renders a bad
 * slot (✕ + slug) instead of a broken glyph — one missing image never
 * takes the panel down. A changed src clears the state, so a regenerated
 * file served under the same url path retries on display. */
export function AssetImg({ src, alt, className, loading = "lazy" }: {
  src: string;
  alt: string;
  className?: string;
  loading?: "lazy" | "eager";
}) {
  const [bad, setBad] = useState(false);
  useEffect(() => { setBad(false); }, [src]);
  if (bad) {
    return (
      <span className={`img-bad ${className ?? ""}`}
        data-testid={`bad-img-${alt}`}
        title={`${alt} — file failed to load`}>
        <span className="img-bad-x" aria-hidden>✕</span>
        <span className="img-bad-slug">{alt}</span>
      </span>
    );
  }
  return (
    <img src={src} alt={alt} className={className} loading={loading}
      onError={() => setBad(true)} />
  );
}
