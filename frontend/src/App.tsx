import { useState } from "react";
import { useApi, type Answers, type PainPoints, type Summary } from "./api";
import { Docket, type StopId } from "./components/Docket";
import { Farm } from "./screens/Farm";
import { Pain } from "./screens/Pain";
import { Plan } from "./screens/Plan";
import { SourcesProvider } from "./sources";

export default function App() {
  const [stop, setStop] = useState<StopId>("farm");
  // The goal and the farmer's answers live here so they survive moving between screens.
  const [pct, setPct] = useState<number | null>(null);
  const [answers, setAnswers] = useState<Answers>({});
  // "Not sure" is kept too, but it is the absence of an answer, so it never goes to the API.
  const [unsure, setUnsure] = useState<Partial<Record<keyof Answers, boolean>>>({});
  const summary = useApi<Summary>("/api/farms/a/summary");
  const pain = useApi<PainPoints>("/api/farms/a/pain-points");

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
  const attribution = s ? `${s.provenance.dataset}. ${s.provenance.licence}. ${s.provenance.attribution}` : undefined;

  return (
    <SourcesProvider>
      <Docket current={stop} onGo={setStop} attribution={attribution}>
        {stop === "farm" && <Farm summary={summary} pain={pain} onNext={() => setStop("pain")} />}
        {stop === "pain" && <Pain pain={pain} onNext={() => setStop("plan")} />}
        {stop === "plan" && <Plan pct={pct} setPct={setPct} answers={answers} unsure={unsure} onAnswer={onAnswer} />}
      </Docket>
    </SourcesProvider>
  );
}
