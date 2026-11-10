import type { ReactNode } from "react";
import styles from "./pageHeadingStyles";

type PageHeadingProps = {
  title: string;
  description: string;
  meta?: string;
  actions?: ReactNode;
  headingLevel?: 1 | 2;
  className?: string;
};

export function PageHeading({
  title,
  description,
  meta,
  actions,
  headingLevel = 1,
  className,
}: PageHeadingProps) {
  const Heading = headingLevel === 1 ? "h1" : "h2";
  return (
    <header
      className={[styles.heading, className].filter(Boolean).join(" ")}
      data-meta-only={meta && !actions ? true : undefined}
    >
      <div className={styles.copy}>
        <Heading className={styles.title}>{title}</Heading>
        <p className={styles.description}>{description}</p>
      </div>
      {(meta || actions) && (
        <div className={styles.actions}>
          {meta && <span className={styles.meta}>{meta}</span>}
          {actions}
        </div>
      )}
    </header>
  );
}
