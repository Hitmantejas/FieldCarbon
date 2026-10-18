import { Shell } from "./components/Shell";
import { useRoute } from "./route";
import { Ask } from "./screens/Ask";
import { Clients } from "./screens/Clients";
import { FuelControl } from "./screens/FuelControl";
import { Jobs } from "./screens/Jobs";
import { Opportunities } from "./screens/Opportunities";
import { Overview } from "./screens/Overview";
import { Proof } from "./screens/Proof";
import { Reports } from "./screens/Reports";
import { Sites } from "./screens/Sites";
import { Trust } from "./screens/Trust";
import { WhatIf } from "./screens/WhatIf";
import { SourcesProvider } from "./sources";

const ATTRIBUTION =
  "Real telemetry: TUM Agricultural Load Cycles (Zenodo 14619787), vineyard tractor operations (Mendeley Data, DOI 10.17632/y3h5xzkjc6.1) and Tümosan tillage CAN bus (DOI 10.17632/bbjtjrsxvx.2), all CC BY 4.0, aggregated by us. Emission factors: UK Government GHG Conversion Factors 2025 (OGL). Operators, clients, fuel deliveries and maintenance are synthetic.";

export default function App() {
  const [screen, go] = useRoute();
  return (
    <SourcesProvider>
      <Shell current={screen} onGo={go} attribution={ATTRIBUTION}>
        {screen === "overview" && <Overview />}
        {screen === "ask" && <Ask />}
        {screen === "clients" && <Clients />}
        {screen === "jobs" && <Jobs />}
        {screen === "whatif" && <WhatIf />}
        {screen === "reports" && <Reports />}
        {screen === "sites" && <Sites />}
        {screen === "opportunities" && <Opportunities />}
        {screen === "proof" && <Proof />}
        {screen === "control" && <FuelControl />}
        {screen === "trust" && <Trust />}
      </Shell>
    </SourcesProvider>
  );
}
