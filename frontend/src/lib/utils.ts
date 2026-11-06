import { clsx, type ClassValue } from "clsx";
import { extendTailwindMerge } from "tailwind-merge";

// These are font sizes, not colours, even though both use Tailwind’s text prefix.
const mergeClasses = extendTailwindMerge({
  extend: {
    classGroups: {
      "font-size": [{ text: ["body", "section"] }],
      rounded: [{ rounded: ["field"] }],
    },
  },
});

export function cn(...inputs: ClassValue[]) {
  return mergeClasses(clsx(inputs));
}
