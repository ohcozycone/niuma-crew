import { createContext } from "react";

export const CitationContext = createContext<{
  titles: ReadonlyMap<string, string>;
  streaming: boolean;
  sourceRunId?: string;
}>({ titles: new Map(), streaming: false });
