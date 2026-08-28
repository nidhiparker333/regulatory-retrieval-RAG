export type Passage = {
  n: number;
  citation: string;
  score: number | null;
  source: string;
  title: string;
  text: string;
};

export type TraceStep = {
  step: string;
  detail: string;
  ms?: number;
  tokens_in?: number;
  tokens_out?: number;
  cost_usd?: number;
  results?: { citation: string; score?: number; source?: string }[];
};

export type AskResult = {
  question: string;
  answer: string | null;
  refused: boolean;
  uncited: boolean;
  citations_used: { n: number; citation: string }[];
  passages: Passage[];
  trace: TraceStep[];
  cost_usd: number;
  elapsed_ms: number;
};
