export function RouteLoadingFallback() {
  return (
    <div
      style={{
        display: 'grid',
        placeItems: 'center',
        padding: 24,
        minHeight: 240,
        width: '100%',
      }}
      aria-label="Loading"
    >
      Loading…
    </div>
  );
}

