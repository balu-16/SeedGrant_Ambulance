/**
 * ADMIN System (plan §4.1) — force sweep (POST /admin/sweep via the shared
 * request client, result counts rendered once it returns) and the
 * /admin/config-check report rendered as a definition list Card.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { request } from "@/services/api";
import { fetchMqttHealth } from "@/services/portal";
import { Button, Card, PageHeader, SectionTitle, Txt } from "@/components/ui";
import { fmtDateTime, fmtValue } from "@/pages/admin/shared";
import { ErrorCard, KVList, LoadingBlock } from "@/pages/admin/widgets";
import "@/pages/admin/admin.css";

interface SweepResult {
  at: string;
  data: Record<string, unknown>;
}

export function SystemPage() {
  const qc = useQueryClient();
  const config = useQuery({
    queryKey: ["admin", "config-check"],
    queryFn: () => request<Record<string, unknown>>("/admin/config-check"),
  });
  const mqtt = useQuery({
    queryKey: ["admin", "mqtt-health"],
    queryFn: fetchMqttHealth,
    refetchInterval: 10_000,
  });

  const [sweep, setSweep] = useState<SweepResult | null>(null);
  const sweepM = useMutation({
    mutationFn: () => request<Record<string, unknown>>("/admin/sweep", { method: "POST" }),
    onSuccess: (data) => {
      setSweep({ at: new Date().toISOString(), data });
      void qc.invalidateQueries({ queryKey: ["admin", "devices"] });
      void qc.invalidateQueries({ queryKey: ["admin", "live"] });
    },
  });

  return (
    <div className="page-body">
      <PageHeader
        title="System"
        subtitle="Sweeps, config checks, retention and MQTT health"
      >
        <Button
          tone="danger"
          title="Force sweep"
          icon="bolt"
          loading={sweepM.isPending}
          onClick={() => sweepM.mutate()}
        />
      </PageHeader>

      {sweepM.isError && (
        <ErrorCard
          title="Sweep failed"
          error={sweepM.error}
          onRetry={() => sweepM.reset()}
        />
      )}

      {sweep && (
        <Card>
          <Txt as="div" style={{ fontWeight: 600, marginBottom: 4 }}>
            Last sweep result
          </Txt>
          <Txt muted className="admin-mono" style={{ marginBottom: 10 }}>
            ran {fmtDateTime(sweep.at)}
          </Txt>
          <KVList
            entries={Object.entries(sweep.data).map(
              ([k, v]) => [k, fmtValue(v)] as [string, string],
            )}
          />
        </Card>
      )}

      <SectionTitle>MQTT health</SectionTitle>
      {mqtt.isError ? (
        <ErrorCard
          title="Could not load MQTT health"
          error={mqtt.error}
          onRetry={() => void mqtt.refetch()}
        />
      ) : mqtt.isLoading ? (
        <LoadingBlock label="Checking MQTT broker" />
      ) : (
        <Card>
          <KVList
            entries={Object.entries(mqtt.data ?? {}).map(
              ([k, v]) => [k, fmtValue(v)] as [string, string],
            )}
          />
        </Card>
      )}

      <SectionTitle>Configuration check</SectionTitle>

      {config.isError ? (
        <ErrorCard
          title="Could not load the configuration check"
          error={config.error}
          onRetry={() => void config.refetch()}
        />
      ) : config.isLoading ? (
        <LoadingBlock label="Running config check" />
      ) : (
        <Card>
          <dl className="admin-kv">
            {Object.entries(config.data ?? {}).map(([k, v]) => (
              <div className="admin-kv-row" key={k}>
                <dt>{k}</dt>
                <dd>{fmtValue(v)}</dd>
              </div>
            ))}
          </dl>
          {Object.keys(config.data ?? {}).length === 0 && (
            <Txt muted>The backend reported no configuration entries.</Txt>
          )}
        </Card>
      )}

      <Txt muted>
        The sweep scans for expired commands, timed-out sessions and offline
        devices outside the regular schedule; results appear above as soon as
        the backend responds.
      </Txt>
    </div>
  );
}
