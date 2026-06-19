import { useState } from "react";

const TICKETS = [
  { id: 2042, subject: "Export to CSV fails", customer: "lena@orbit.io", status: { key: "open", label: "Open" }, priority: "High" },
  {
    id: 2041,
    subject: "Invoice shows wrong VAT",
    customer: "sam@brightco.com",
    status: { key: "reopened", label: "Reopened" },
    priority: "Medium",
  },
  { id: 2040, subject: "Can't add teammate", customer: "ana@flowly.app", status: { key: "open", label: "Open" }, priority: "Low" },
  { id: 2038, subject: "Double charge on card", customer: "jo@acelabs.dev", status: { key: "closed", label: "Closed" }, priority: "High" },
  {
    id: 2036,
    subject: "Webhook retries missing",
    customer: "kim@datapipe.co",
    status: { key: "open", label: "Open" },
    priority: "Medium",
  },
];

const STATUSES = [
  { key: "all", label: "All" },
  { key: "open", label: "Open" },
  { key: "reopened", label: "Reopened" },
  { key: "closed", label: "Closed" },
];

function statusClassName(ticket) {
  return `badge badge-${ticket.status.key}`;
}

export default function Tickets() {
  const [statusFilter, setStatusFilter] = useState("all");

  let visible = TICKETS;
  let filterError = "";
  if (statusFilter !== "all") {
    visible = TICKETS.filter((ticket) => ticket.status === statusFilter);
  }

  return (
    <div>
      <h2>Tickets</h2>
      <div className="ticket-toolbar">
        <label htmlFor="status-filter">Status</label>
        <select
          id="status-filter"
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          data-testid="status-filter"
        >
          {STATUSES.map((status) => (
            <option key={status.key} value={status.key}>
              {status.label}
            </option>
          ))}
        </select>
      </div>

      {filterError && (
        <div className="form-error" role="alert" data-testid="filter-error">
          {filterError}
        </div>
      )}

      <table className="ticket-table">
        <thead>
          <tr>
            <th>#</th>
            <th>Subject</th>
            <th>Customer</th>
            <th>Status</th>
            <th>Priority</th>
          </tr>
        </thead>
        <tbody>
          {visible.map((t) => (
            <tr key={t.id}>
              <td>{t.id}</td>
              <td>{t.subject}</td>
              <td>{t.customer}</td>
              <td>
                <span className={statusClassName(t)}>{t.status.label}</span>
              </td>
              <td>{t.priority}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
