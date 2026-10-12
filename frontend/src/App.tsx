import { useState } from "react";
import { useApi, type PainPoints, type Summary } from "./api";
import { Docket, type StopId } from "./components/Docket";
import { Farm } from "./screens/Farm";
import { Pain } from "./screens/Pain";
import { Plan } from "./screens/Plan";
import { SourcesProvider } from "./sources";

export default function App() {
  const [stop, setStop] = useState<StopId>("farm");
  const summary = useApi<Summary>("/api/farms/a/summary");
  const pain = useApi<PainPoints>("/api/farms/a/pain-points");

  const s = summary.data;
  const attribution = s ? `${s.provenance.dataset}. ${s.provenance.licence}. ${s.provenance.attribution}` : undefined;

  return (
    <SourcesProvider>
      <Docket current={stop} onGo={setStop} attribution={attribution}>
        {stop === "farm" && <Farm summary={summary} pain={pain} onNext={() => setStop("pain")} />}
        {stop === "pain" && <Pain pain={pain} onNext={() => setStop("plan")} />}
        {stop === "plan" && <Plan />}
      </Docket>
    </SourcesProvider>
  );
}
