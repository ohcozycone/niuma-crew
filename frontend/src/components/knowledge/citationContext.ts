import { createContext } from "react";

export const CitationContext = createContext<{
  titles: ReadonlyMap<string, string>;
  streaming: boolean;
}>({ titles: new Map(), streaming: false });
