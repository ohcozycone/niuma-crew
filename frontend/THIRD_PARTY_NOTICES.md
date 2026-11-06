# Third-party components

Execution evidence uses the unmodified MIT-licensed
[`@uiw/react-json-view`](https://github.com/uiwjs/react-json-view) package through
`src/components/ui/JsonInspector.tsx`. The read-only adapter maps its public theme
variables to product tokens and provides keyboard-accessible node controls and
JSON copying. The upstream license remains in the installed package.

Markdown is rendered by unmodified Streamdown with its CJK and code plugins
through `src/components/common/Markdown.tsx`. Its public theme
variables map to the product's semantic tokens, with limited styling through
official `data-streamdown` attributes; see
[`src/design-system/colors.md`](src/design-system/colors.md#markdown-渲染器主题).
Its upstream license is retained in the installed package.

`src/components/ui/` contains components from the official
[shadcn/ui registry](https://ui.shadcn.com), new-york-v4 style,
Copyright (c) 2023 shadcn, MIT License. The full license is retained in
`src/components/ui/LICENSE`. Local changes resolve the utility import, apply
the shared semantic tokens and control styles, and translate dialog close labels.
The adapters use Base UI primitives and its render composition interface.
Message, Bubble, Trace, Collapsible and Input Group follow the official Base UI
registry at commit [`e55b60b`](https://github.com/shadcn-ui/ui/tree/e55b60b1014cccfb9ac62f97e0d20b5b649f4a54/apps/v4/registry/bases/base/ui).
Their interaction structure is retained and the local classes use the existing
product tokens, including typography, colours, radius and focus.
`HoverCard.tsx` follows the official Base UI
[`hover-card` registry composition](https://github.com/shadcn-ui/ui/blob/main/apps/v4/registry/bases/base/ui/hover-card.tsx),
using the installed Base UI Preview Card primitive. `KnowledgeInlineCitation.tsx`,
`KnowledgeSources.tsx` and `Sources.tsx` follow the official
[Inline Citation](https://ui.shadcn.com/docs/ai-elements/base/inline-citation)
and [Sources](https://ui.shadcn.com/docs/ai-elements/base/sources) patterns,
with private-document titles, bounded owner-scoped previews, Chinese accessible
labels and click access for touch devices. These are copied component compositions,
not a dependency on Vercel AI SDK. The shadcn MIT notice above applies.
Pagination follows the official Base UI pagination composition, using the local
Button adapter for URL-driven page actions, Chinese accessible labels and
icon-only previous/next controls.
Field follows the shadcn label/control/description/error composition and applies
the shared field typography on Base UI semantics. Input, Textarea, Select and
Input Group share a themed focus border and translucent ring.
Base UI is distributed under the MIT License; its notice is retained in
the installed `@base-ui/react` package.

`src/components/ui/MessageScroller.tsx` styles the unmodified
`@shadcn/react/message-scroller` primitive, Copyright (c) shadcn, MIT License.
Scroll following, opening position and prepend preservation remain owned by the
package; pagination requests remain in the conversation page. The upstream
license is retained in the installed `@shadcn/react` package.
