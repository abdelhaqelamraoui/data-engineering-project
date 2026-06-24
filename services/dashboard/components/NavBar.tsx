"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  { href: "/", label: "Trending" },
  { href: "/live", label: "Live posts" },
  { href: "/preprocessing", label: "Preprocessing" },
];

export function NavBar() {
  const pathname = usePathname();

  return (
    <nav className="nav">
      <div className="nav-inner">
        <span className="nav-brand">Trending Topics</span>
        <div className="nav-links">
          {LINKS.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className={pathname === link.href ? "active" : ""}
            >
              {link.label}
            </Link>
          ))}
        </div>
      </div>
    </nav>
  );
}
