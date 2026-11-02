import { createElement, useId, type ReactElement, type SVGProps } from "react";

export type CharacterSvgProps = Omit<
  SVGProps<SVGSVGElement>,
  "children" | "dangerouslySetInnerHTML" | "viewBox" | "width" | "height"
> & {
  size?: number | string;
  /** Empty means decorative; provide a label when the avatar conveys identity. */
  alt?: string;
  /** Any SVG color; transparent by default. */
  background?: string;
};

export type ArtworkNode = {
  readonly tag: string;
  readonly attrs: Readonly<Record<string, string>>;
  readonly children?: readonly ArtworkNode[];
};
export type SvgArtwork = {
  readonly character: string;
  readonly nodes: readonly ArtworkNode[];
};

const attributeNames: Record<string, string> = {
  "clip-path": "clipPath",
  "mask-type": "maskType",
  "clip-rule": "clipRule",
  "fill-rule": "fillRule",
  "stop-color": "stopColor",
  "stop-opacity": "stopOpacity",
  "stroke-width": "strokeWidth",
};
function artworkNode(node: ArtworkNode, prefix: string, key: number): ReactElement {
  const attrs: Record<string, string | number> = { key };
  for (const [name, value] of Object.entries(node.attrs)) {
    const prop = attributeNames[name] ?? name;
    attrs[prop] =
      name === "id"
        ? `${prefix}-${value}`
        : value.replace(/url\(#([^)]+)\)/g, `url(#${prefix}-$1)`);
    if (name === "id" && ["path", "ellipse", "g"].includes(node.tag)) attrs["data-part"] = value;
  }
  return createElement(
    node.tag,
    attrs,
    node.children?.map((child, i) => artworkNode(child, prefix, i)),
  );
}

/** Render trusted bundled vector data; no fetch, bitmap, animation or runtime. */
export function ArtworkFrame({
  artwork,
  size = 96,
  alt = "",
  background = "transparent",
  style,
  ...props
}: CharacterSvgProps & { artwork: SvgArtwork }) {
  const prefix = `niuma-${useId().replace(/[^a-zA-Z0-9_-]/g, "")}`;
  const labelled = Boolean(alt || props["aria-label"] || props["aria-labelledby"]);
  return (
    <svg
      {...props}
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 1254 1254"
      width={size}
      height={size}
      role={labelled ? "img" : undefined}
      aria-label={alt || props["aria-label"]}
      aria-hidden={labelled ? undefined : true}
      focusable={props.focusable ?? false}
      data-avatar-character={artwork.character}
      style={{
        display: "inline-block",
        width: size,
        height: size,
        aspectRatio: "1",
        verticalAlign: "middle",
        flexShrink: 0,
        ...style,
      }}
    >
      {alt ? <title>{alt}</title> : null}
      {background !== "transparent" ? <rect width="1254" height="1254" fill={background} /> : null}
      {artwork.nodes.map((node, i) => artworkNode(node, prefix, i))}
    </svg>
  );
}
