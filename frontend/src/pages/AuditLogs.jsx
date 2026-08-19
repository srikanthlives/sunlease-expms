import { useEffect, useState } from "react";
import client from "../api/client";
import { Card, Table } from "../components/ui";

export default function AuditLogs() {
  const [logs, setLogs] = useState([]);
  useEffect(() => { client.get("/audit-logs").then((res) => setLogs(res.data)); }, []);
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-display font-semibold">Audit Logs</h1>
        <p className="text-sm text-ink/50 mt-0.5">Immutable record of every create, approve, reject and payment action.</p>
      </div>
      <Card>
        <Table
          columns={[
            { key: "created_at", header: "Time", render: (r) => new Date(r.created_at).toLocaleString() },
            { key: "entity_type", header: "Entity" },
            { key: "entity_id", header: "ID" },
            { key: "action", header: "Action" },
            { key: "actor_id", header: "Actor" },
            { key: "details", header: "Details", render: (r) => <span className="text-xs text-ink/40 font-mono">{r.details}</span> },
          ]}
          rows={logs}
        />
      </Card>
    </div>
  );
}
