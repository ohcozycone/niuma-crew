/** Project adapters expose static Tailwind class combinations. */
export type StyledProps<Props> = Omit<Props, "className"> & { className?: string };
