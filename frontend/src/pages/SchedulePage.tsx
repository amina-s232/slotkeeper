import { useQuery } from "@tanstack/react-query";
import * as api from "../api/endpoints";
import { ErrorBanner } from "../components/ErrorBanner";
import { RulesPanel } from "../components/RulesPanel";
import { SettingsPanel } from "../components/SettingsPanel";
import { TimeOffPanel } from "../components/TimeOffPanel";

export function SchedulePage() {
  const provider = useQuery({ queryKey: ["own-provider"], queryFn: api.getOwnProvider });
  if (provider.isPending) return <p>Loading…</p>;
  if (provider.error) return <ErrorBanner error={provider.error} />;
  return (
    <section>
      <h1>Schedule</h1>
      <RulesPanel />
      <TimeOffPanel timezone={provider.data.timezone} />
      <SettingsPanel provider={provider.data} />
    </section>
  );
}
