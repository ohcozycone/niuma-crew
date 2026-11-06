import { useTheme } from "@/state/theme/useTheme";
import { brand } from "@/lib/brand";
import styles from "./brandLogoStyles";

export function BrandLogo({ subtitle = false }: { subtitle?: boolean }) {
  const { resolved } = useTheme();
  return (
    <span className={styles.logo}>
      <img
        src={resolved === "dark" ? brand.wordmarkDark : brand.wordmark}
        width={158}
        height={40}
        alt={subtitle ? `${brand.name} · ${brand.tagline}` : brand.name}
      />
    </span>
  );
}
