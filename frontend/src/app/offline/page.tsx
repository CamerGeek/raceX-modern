export default function OfflinePage() {
  return (
    <main className="offline-page">
      <section>
        <span className="offline-mark" aria-hidden="true">RX</span>
        <p className="offline-kicker">RACEX ANALYSIS DESK</p>
        <h1>You’re offline</h1>
        <p>Reconnect to the internet to load meetings and race analysis. Race data is not stored for offline use.</p>
        <form action="/offline" method="get">
          <button type="submit">Try again</button>
        </form>
      </section>
    </main>
  );
}
