import type { Citation } from "../api/types";

export type UiMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  refused?: boolean;
  citations?: Citation[];
};
