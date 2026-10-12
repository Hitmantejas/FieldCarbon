import { useState } from "react";
import { useApi, type Answers, type FarmId, type PainPoints, type Summary } from "./api";
import { Docket, type StopId } from "./components/Docket";
import { Farm } from "./screens/Farm";
import { Pain } from "./screens/Pain";
import { Plan } from "./screens/Plan";
import { Report } from "./screens/Report";
import { Sharpen } from "./screens/Sharpen";
import { SourcesProvider } from "./sources";

export default function App() {
  const [stop, setStop] = useState<StopId>("farm");
  // Both farms are the same real farm, so the goal and the answers carry over when switching.
  const [farm, setFarm] = useState<FarmId>("a");
  // The goal and the farmer's answers live here so they survive moving between screens.
  const [pct, setPct] = useState<number | null>(null);
  const [answers, setAnswers] = useState<Answers>({});
  // "Not sure" is kept too, but it is the absence of an answer, so it never goes to the API.
  const [unsure, setUnsure] = useState<Partial<Record<keyof Answers, boolean>>>({});
  const summary = useApi<Summary>(`/api/farms/${farm}/summary`);
  const pain = useApi<PainPoints>(`/api/farms/${farm}/pain-points`);

  const onAnswer = (field: keyof Answers, value: boolean | string | undefined) => {
    setAnswers((a) => {
      const next = { ...a } as Record<string, unknown>;
      if (value === undefined || value === "unsure") delete next[field];
      else next[field] = value;
      return next as Answers;
    });
    setUnsure((u) => {
      const next = { ...u };
      if (value === "unsure") next[field] = true;
      else delete next[field];
      return next;
    });
  };

  const s = summary.data;
  const p = s?.provenance;
  const attribution = p
    ? [p.dataset, p.licence, p.attribution, p.fuel_use_rates, p.data_source && `Source: ${p.data_source}`].filter(Boolean).join(". ")
    : undefined;

  return (
    <SourcesProvider>
      <Docket current={stop} onGo={setStop} farm={farm} onFarm={setFarm} attribution={attribution}>
        {stop === "farm" && <Farm farm={farm} summary={summary} pain={pain} onNext={() => setStop("pain")} />}
        {stop === "pain" && <Pain pain={pain} onNext={() => setStop("plan")} />}
        {stop === "plan" && (
          <Plan farm={farm} pct={pct} setPct={setPct} answers={answers} unsure={unsure} onAnswer={onAnswer} onNext={() => setStop("sharpen")} />
        )}
        {stop === "sharpen" && (
          <Sharpen farm={farm} pct={pct} answers={answers} unsure={unsure} onAnswer={onAnswer} onNext={() => setStop("report")} />
        )}
        {stop === "report" && <Report farm={farm} pct={pct} answers={answers} />}
      </Docket>
    </SourcesProvider>
  );
}
