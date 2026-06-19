const STATS = [
  { label: "Open tickets", value: 14 },
  { label: "Avg. first response", value: "42m" },
  { label: "CSAT (30d)", value: "94%" },
  { label: "Agents online", value: 3 },
];

export default function Dashboard() {
  return (
    <div>
      <h2>Dashboard</h2>
      <div className="stat-grid">
        {STATS.map((s) => (
          <div className="stat-card" key={s.label}>
            <div className="stat-value">{s.value}</div>
            <div className="stat-label">{s.label}</div>
          </div>
        ))}
      </div>
      <div className="panel">
        <h3>Today</h3>
        <ul className="activity">
          <li>09:12 — Ticket #2041 reopened by customer</li>
          <li>10:05 — Maya closed ticket #2038 (billing)</li>
          <li>11:30 — New ticket #2042: "Export to CSV fails"</li>
          <li>13:47 — SLA warning on ticket #2036</li>
        </ul>
      </div>
    </div>
  );
}
