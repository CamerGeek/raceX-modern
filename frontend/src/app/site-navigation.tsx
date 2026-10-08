import Link from "next/link";

type SiteNavigationProps = {
  currentPage: "home" | "analysis";
};

export default function SiteNavigation({ currentPage }: SiteNavigationProps) {
  return (
    <nav className="site-navigation" aria-label="Navigation principale">
      <Link href="/" aria-current={currentPage === "home" ? "page" : undefined}>
        Quinté du jour
      </Link>
      <Link href="/admin" aria-current={currentPage === "analysis" ? "page" : undefined}>
        Analyse des courses
      </Link>
    </nav>
  );
}
