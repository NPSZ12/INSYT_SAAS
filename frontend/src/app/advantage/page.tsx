"use client";

import { useEffect, useState } from "react";
import Image from "next/image";
import Link from "next/link";

import {
  ArrowRight,
  Building2,
  CheckCircle2,
  ChevronDown,
  FileSearch,
  Layers3,
  Menu,
  ShieldCheck,
  Sparkles,
  X,
} from "lucide-react";

type StoredUser = {
  username: string;
  display_name?: string;
  role?: string;
};

type Product = {
  name: string;
  description: string;
  overviewHighlight: string;
  icon: React.ElementType;
  features: string[];
  href: string;
  screenshot?: string;
  screenshotAlt?: string;
};

type SelectedScreenshot = {
  src: string;
  alt: string;
  title: string;
};

type Insyt360BrandProps = {
  className?: string;
  lightBackground?: boolean;
  alignment?: "raise" | "default" | "lower";
};

function Insyt360Brand({
  className = "",
  lightBackground = false,
  alignment = "default",
}: Insyt360BrandProps) {
  const primaryText = lightBackground
    ? "text-sky-700"
    : "text-white";

  const alignmentClass =
    alignment === "raise"
      ? "mb-[0.30em]"
      : alignment === "lower"
        ? "mb-[0.12em]"
        : "mb-[0.22em]";

  return (
    <span
      className={`insyt-brand inline-flex items-end gap-0 whitespace-nowrap ${className}`}
      aria-label="INSYT360"
    >
      <span className={primaryText}>I</span>
      <span className="text-sky-400">N</span>
      <span className={primaryText}>SYT</span>

      <span
        className={`insyt-brand text-[0.75em] font-bold leading-none text-sky-400 ${alignmentClass}`}
      >
        360
      </span>
    </span>
  );
}

const navigationItems = [
  {
    label: "Why INSYT",
    href: "#why-insyt",
  },
  {
    label: "Products",
    href: "#products",
  },
  {
    label: "Industries",
    href: "#industries",
  },
  {
    label: "Pricing",
    href: "#pricing",
  },
  {
    label: "Demo Gallery",
    href: "#demo-gallery",
  },
  {
    label: "Contact",
    href: "#contact",
  },
];

const products: Product[] = [
  {
    name: "INSYT Capture",
    description:
      "Protocol-driven cyber incident response workflows for identifying, reviewing, validating, and reporting sensitive information.",
    overviewHighlight:
      "Sensitive-data detection, protocol-driven review, entity validation, reporting, and final deliverable overlays.",
    icon: ShieldCheck,
    features: [
      "PII, PHI, and regulatory data review",
      "Protocol-based entity validation",
      "Final deliverable overlays",
    ],
    href: "/capture/projects",
  },
  {
    name: "INSYT Discovery",
    description:
      "Structured eDiscovery processing and review workflows designed to reduce review volume and improve project consistency.",
    overviewHighlight:
      "Document processing, advanced search, batching, first-level review, quality control, and production workflows.",
    icon: FileSearch,
    features: [
      "Document processing and review",
      "Search, batching, and quality control",
      "Production-ready project workflows",
    ],
    href: "/discovery/projects",
  },
  {
    name: "INSYT Summaries",
    description:
      "Collaborative summary review for medical records, depositions, claim files, and other large document collections.",
    overviewHighlight:
      "Linked source-document navigation, collaborative summary review, editable QC, and completed-summary delivery.",
    icon: Layers3,
    features: [
      "Concurrent summary review",
      "Human quality-control workflows",
      "Linked source-document navigation",
    ],
    href: "/summaries/projects",
    screenshot: "/advantage/insyt-summaries.png",
    screenshotAlt:
      "INSYT Summaries document viewer and Summary QC Review workspace",
  },
  {
    name: "Cyber² Utility Suite",
    description:
      "Internal data-processing utilities that prepare, normalize, merge, deduplicate, and organize project information.",
    overviewHighlight:
      "File conversion, normalization, spreadsheet processing, header mapping, merging, and deduplication utilities.",
    icon: Sparkles,
    features: [
      "Spreadsheet conversion and normalization",
      "Header mapping and deduplication",
      "Repeatable processing workflows",
    ],
    href: "/cyber-utility",
  },
];

const industries = [
  {
    title: "Law Firms",
    description:
      "Support litigation, investigations, discovery, document review, and defensible legal workflows.",
  },
  {
    title: "Cyber Incident Response",
    description:
      "Identify and validate sensitive information following security and privacy incidents.",
  },
  {
    title: "Insurance and Claims",
    description:
      "Organize claim records, supporting documents, damages, and structured review findings.",
  },
  {
    title: "Healthcare",
    description:
      "Review medical records and protected health information within controlled workflows.",
  },
  {
    title: "Corporate Legal Departments",
    description:
      "Centralize legal review projects, project data, reporting, and long-term access.",
  },
  {
    title: "Government and Regulatory",
    description:
      "Support structured review requirements involving privacy, compliance, and investigations.",
  },
];

const advantages = [
  "Concentrates human review where professional judgment matters most.",
  "Connects final work product directly to the underlying documents.",
  "Supports repeatable workflows across clients, projects, and review teams.",
  "Reduces manual processing through structured automation and AI-assisted review.",
  "Preserves project information in a centralized, accessible workspace.",
  "Built for legal, privacy, cybersecurity, and document-intensive matters.",
];

export default function AdvantagePage() {
  const [user, setUser] = useState<StoredUser | null>(null);
  const [authChecked, setAuthChecked] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  const [selectedScreenshot, setSelectedScreenshot] =
    useState<SelectedScreenshot | null>(null);

  useEffect(() => {
    const storedUser = localStorage.getItem("insyt_user");

    if (!storedUser) {
        window.location.href =
        `/login?next=${encodeURIComponent("/advantage")}`;
        return;
    }

    try {
        setUser(JSON.parse(storedUser));
        setAuthChecked(true);
    } catch (error) {
        console.error("Unable to parse stored INSYT user.", error);

        localStorage.removeItem("insyt_user");
        localStorage.removeItem("insyt_access_token");

        window.location.href =
        `/login?next=${encodeURIComponent("/advantage")}`;
    }
    }, []);

  useEffect(() => {
    if (!selectedScreenshot) {
      return;
    }

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setSelectedScreenshot(null);
      }
    }

    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", handleKeyDown);

    return () => {
      document.body.style.overflow = "";
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [selectedScreenshot]);

  function closeMobileMenu() {
    setMobileMenuOpen(false);
  }

  function openProductScreenshot(product: Product) {
    if (!product.screenshot) {
      return;
    }

    setSelectedScreenshot({
      src: product.screenshot,
      alt:
        product.screenshotAlt ??
        `${product.name} screenshot`,
      title: product.name,
    });
  }

  if (!authChecked) {
    return (
        <main className="min-h-screen bg-slate-950" />
    );
  }

  return (
    <main className="min-h-screen scroll-smooth bg-slate-950 text-white">
      <header className="sticky top-0 z-50 border-b border-slate-800 bg-slate-950/95 backdrop-blur">
        <div className="mx-auto flex h-20 max-w-7xl items-center justify-between px-6 lg:px-10">
          <Link
            href="/launcher"
            className="flex items-center"
            aria-label="Return to INSYT360 Launcher"
          >
            <Insyt360Brand
              className="text-4xl font-bold"
              alignment="lower"
            />
          </Link>

          <nav className="hidden items-center gap-7 xl:flex">
            {navigationItems.map((item) => (
              <a
                key={item.href}
                href={item.href}
                className="text-sm font-medium text-slate-300 transition hover:text-sky-400"
              >
                {item.label}
              </a>
            ))}
          </nav>

          <div className="hidden items-center md:flex">
            <Link
              href="/launcher"
              className="rounded-xl border-2 border-sky-400 bg-sky-500 px-5 py-2.5 text-sm font-semibold text-black shadow-md transition hover:border-sky-300 hover:bg-sky-400"
            >
              Launcher
            </Link>
          </div>

          <button
            type="button"
            onClick={() =>
              setMobileMenuOpen((current) => !current)
            }
            className="rounded-xl border border-slate-700 p-2.5 text-slate-200 md:hidden"
            aria-label="Toggle navigation"
          >
            {mobileMenuOpen ? (
              <X size={22} />
            ) : (
              <Menu size={22} />
            )}
          </button>
        </div>

        {mobileMenuOpen && (
          <div className="border-t border-slate-800 bg-slate-950 px-6 py-5 md:hidden">
            <nav className="flex flex-col gap-4">
              {navigationItems.map((item) => (
                <a
                  key={item.href}
                  href={item.href}
                  onClick={closeMobileMenu}
                  className="text-base font-medium text-slate-300 hover:text-sky-400"
                >
                  {item.label}
                </a>
              ))}

              <div className="mt-2">
                <Link
                  href="/launcher"
                  onClick={closeMobileMenu}
                  className="block w-full rounded-xl border-2 border-sky-400 bg-sky-500 px-4 py-3 text-center text-sm font-semibold text-black shadow-md transition hover:border-sky-300 hover:bg-sky-400"
                >
                  Launcher
                </Link>
              </div>
            </nav>
          </div>
        )}
      </header>

      <section className="relative overflow-hidden border-b border-slate-800">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_right,rgba(14,165,233,0.16),transparent_40%)]" />

        <div className="relative mx-auto grid min-h-[720px] max-w-7xl items-center gap-14 px-6 py-24 lg:grid-cols-[1.1fr_0.9fr] lg:px-10">
          <div>
            <div className="mb-6 inline-flex items-center gap-2 rounded-full border border-sky-500/30 bg-sky-500/10 px-4 py-2 text-sm font-semibold text-sky-300">
              <Sparkles size={16} />
              INSYT Advantage
            </div>

            <h1 className="max-w-4xl text-5xl font-bold leading-tight text-white md:text-6xl lg:text-7xl">
              <span>Explore </span>
              <Insyt360Brand />
            </h1>

            <p className="mt-7 max-w-3xl text-xl leading-relaxed text-slate-300">
              A unified review and intelligence platform built for
              document-intensive legal, cybersecurity, privacy, and
              investigative workflows.
            </p>

            <p className="mt-5 max-w-3xl text-base leading-relaxed text-slate-400">
              <Insyt360Brand alignment="raise" /> combines structured processing, AI-assisted
              analysis, professional human review, quality control, and
              long-term project accessibility within one secure platform.
            </p>

            <div className="mt-10 flex flex-col gap-4 sm:flex-row">
              <a
                href="#products"
                className="inline-flex items-center justify-center gap-2 rounded-xl bg-sky-500 px-6 py-3.5 font-semibold text-slate-950 transition hover:bg-sky-400"
              >
                Explore Products
                <ArrowRight size={18} />
              </a>

              <a
                href="#demo-gallery"
                className="inline-flex items-center justify-center gap-2 rounded-xl border border-slate-700 bg-slate-900/70 px-6 py-3.5 font-semibold text-white transition hover:border-sky-500"
              >
                View Demo Examples
                <ChevronDown size={18} />
              </a>
            </div>
          </div>

          <div className="rounded-3xl border border-slate-700 bg-slate-900/80 p-7 shadow-2xl shadow-sky-950/30">
            <div className="mb-6 flex items-center justify-between">
              <div>
                <p className="text-sm uppercase tracking-[0.2em] text-slate-500">
                  Platform Overview
                </p>

                <h2 className="insyt-workspace mt-2 text-2xl font-bold leading-tight">
                  <span className="block">
                    One Platform.
                  </span>

                  <span className="block">
                    Multiple Workflows.
                  </span>
                </h2>
              </div>

              <div className="rounded-2xl border border-sky-500/30 bg-sky-500/10 p-3 text-sky-400">
                <Layers3 size={26} />
              </div>
            </div>

            <div className="space-y-3">
              {products.map((product) => {
                const Icon = product.icon;

                return (
                  <div
                    key={product.name}
                    className="flex items-center gap-4 rounded-2xl border border-slate-800 bg-slate-950/70 p-4"
                  >
                    <div className="rounded-xl bg-slate-800 p-3 text-sky-400">
                      <Icon size={21} />
                    </div>

                    <div>
                      <p className="insyt-workspace font-semibold text-white">
                        {product.name}
                      </p>

                      <p className="mt-1 max-w-md text-sm leading-relaxed text-slate-400">
                        {product.overviewHighlight}
                      </p>
                    </div>
                  </div>
                );
              })}
            </div>

            <div className="mt-6 border-t border-slate-800 pt-6">
              <Image
                src="/CDS_Logo_W.svg"
                alt="Cyber Discovery Solutions"
                width={250}
                height={60}
                style={{
                  width: "240px",
                  height: "auto",
                }}
              />

              <p className="mt-3 text-sm text-slate-500">
                Powered by Cyber Discovery Solutions
              </p>
            </div>
          </div>
        </div>
      </section>

      <section
        id="why-insyt"
        className="scroll-mt-24 border-b border-slate-800 py-24"
      >
        <div className="mx-auto max-w-7xl px-6 lg:px-10">
          <div className="max-w-3xl">
            <p className="text-sm font-semibold uppercase tracking-[0.2em] text-sky-400">
              Why INSYT
            </p>

            <h2 className="insyt-workspace mt-4 text-4xl font-bold md:text-5xl">
              Review technology designed around the work itself.
            </h2>

            <p className="mt-6 text-lg leading-relaxed text-slate-400">
              <Insyt360Brand alignment="raise" /> is designed to reduce disconnected tools,
              repetitive processing, and unnecessary review effort while
              preserving professional oversight and defensible results.
            </p>
          </div>

          <div className="mt-14 grid gap-5 md:grid-cols-2">
            {advantages.map((advantage) => (
              <div
                key={advantage}
                className="flex gap-4 rounded-2xl border border-slate-800 bg-slate-900 p-5"
              >
                <CheckCircle2
                  size={22}
                  className="mt-0.5 shrink-0 text-sky-400"
                />

                <p className="leading-relaxed text-slate-300">
                  {advantage}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section
        id="products"
        className="scroll-mt-24 border-b border-slate-800 bg-slate-900/30 py-24"
      >
        <div className="mx-auto max-w-7xl px-6 lg:px-10">
          <div className="max-w-3xl">
            <p className="text-sm font-semibold uppercase tracking-[0.2em] text-sky-400">
              Products
            </p>

            <h2 className="insyt-workspace mt-4 text-4xl font-bold md:text-5xl">
              Purpose-built tools working as one platform.
            </h2>
          </div>

          <div className="mt-14 grid gap-6 lg:grid-cols-2">
            {products.map((product) => {
              const Icon = product.icon;

              return (
                <article
                  key={product.name}
                  className="flex flex-col rounded-3xl border border-slate-800 bg-slate-900 p-7 transition hover:border-sky-500/70"
                >
                  <div className="flex items-start justify-between gap-5">
                    <div className="rounded-2xl border border-sky-500/20 bg-sky-500/10 p-4 text-sky-400">
                      <Icon size={28} />
                    </div>
                  </div>

                  <h3 className="insyt-workspace mt-7 text-3xl font-bold">
                    {product.name}
                  </h3>

                  {product.screenshot && (
                    <button
                      type="button"
                      onClick={() => openProductScreenshot(product)}
                      className="group relative mt-6 block w-full overflow-hidden rounded-2xl border border-slate-700 bg-slate-950 text-left transition hover:border-sky-500"
                    >
                      <div className="relative aspect-[16/8.5] w-full overflow-hidden">
                        <Image
                          src={product.screenshot}
                          alt={
                            product.screenshotAlt ??
                            `${product.name} screenshot`
                          }
                          fill
                          sizes="(max-width: 1024px) 100vw, 50vw"
                          className="object-cover object-top transition duration-300 group-hover:scale-[1.02]"
                        />
                      </div>

                      <div className="absolute inset-0 flex items-center justify-center bg-slate-950/0 transition group-hover:bg-slate-950/35">
                        <span className="translate-y-2 rounded-xl border border-white/20 bg-slate-950/90 px-5 py-2.5 text-sm font-semibold text-white opacity-0 shadow-xl transition group-hover:translate-y-0 group-hover:opacity-100">
                          View Full Screenshot
                        </span>
                      </div>
                    </button>
                  )}

                  <p className="mt-4 flex-1 leading-relaxed text-slate-400">
                    {product.description}
                  </p>

                  <div className="mt-6 space-y-3">
                    {product.features.map((feature) => (
                      <div
                        key={feature}
                        className="flex items-start gap-3"
                      >
                        <CheckCircle2
                          size={18}
                          className="mt-0.5 shrink-0 text-sky-400"
                        />

                        <span className="text-sm text-slate-300">
                          {feature}
                        </span>
                      </div>
                    ))}
                  </div>

                  {product.screenshot ? (
                    <button
                      type="button"
                      onClick={() => openProductScreenshot(product)}
                      className="mt-8 inline-flex items-center gap-2 self-start font-semibold text-sky-400 transition hover:text-sky-300"
                    >
                      View Screenshot
                      <ArrowRight size={17} />
                    </button>
                  ) : (
                    <span className="mt-8 inline-flex items-center gap-2 text-sm font-medium text-slate-600">
                      Screenshot coming soon
                    </span>
                  )}
                </article>
              );
            })}
          </div>
        </div>
      </section>

      <section
        id="industries"
        className="scroll-mt-24 border-b border-slate-800 py-24"
      >
        <div className="mx-auto max-w-7xl px-6 lg:px-10">
          <div className="flex max-w-3xl items-start gap-5">
            <div className="rounded-2xl border border-sky-500/20 bg-sky-500/10 p-4 text-sky-400">
              <Building2 size={28} />
            </div>

            <div>
              <p className="text-sm font-semibold uppercase tracking-[0.2em] text-sky-400">
                Industries
              </p>

              <h2 className="insyt-workspace mt-4 text-4xl font-bold md:text-5xl">
                Flexible enough for complex, document-intensive matters.
              </h2>
            </div>
          </div>

          <div className="mt-14 grid gap-5 md:grid-cols-2 xl:grid-cols-3">
            {industries.map((industry) => (
              <article
                key={industry.title}
                className="rounded-2xl border border-slate-800 bg-slate-900 p-6"
              >
                <h3 className="insyt-workspace text-xl font-semibold text-white">
                  {industry.title}
                </h3>

                <p className="mt-4 leading-relaxed text-slate-400">
                  {industry.description}
                </p>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section
        id="pricing"
        className="scroll-mt-24 border-b border-slate-800 bg-slate-900/30 py-24"
      >
        <div className="mx-auto max-w-7xl px-6 lg:px-10">
          <div className="max-w-3xl">
            <p className="text-sm font-semibold uppercase tracking-[0.2em] text-sky-400">
              Pricing
            </p>

            <h2 className="insyt-workspace mt-4 text-4xl font-bold md:text-5xl">
              Pricing aligned with the project.
            </h2>

            <p className="mt-6 text-lg leading-relaxed text-slate-400">
              <Insyt360Brand alignment="raise" /> supports flexible pricing based on project
              volume, workflow requirements, platform access, managed services,
              and the level of professional review required.
            </p>
          </div>

          <div className="mt-14 grid gap-6 lg:grid-cols-3">
            {[
              {
                title: "Project-Based",
                description:
                  "Defined workflows and pricing for individual legal, cyber, investigative, or summary projects.",
              },
              {
                title: "Usage-Based",
                description:
                  "Pricing based on document volume, processing requirements, review scope, or completed work product.",
              },
              {
                title: "Enterprise",
                description:
                  "Ongoing platform access, custom integrations, expanded storage, and tailored organizational workflows.",
              },
            ].map((pricingOption) => (
              <article
                key={pricingOption.title}
                className="rounded-3xl border border-slate-800 bg-slate-900 p-7"
              >
                <h3 className="insyt-workspace text-2xl font-bold">
                  {pricingOption.title}
                </h3>

                <p className="mt-5 leading-relaxed text-slate-400">
                  {pricingOption.description}
                </p>

                <a
                  href="#contact"
                  className="mt-8 inline-flex items-center gap-2 font-semibold text-sky-400 hover:text-sky-300"
                >
                  Request pricing
                  <ArrowRight size={17} />
                </a>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section
        id="demo-gallery"
        className="scroll-mt-24 border-b border-slate-800 py-24"
      >
        <div className="mx-auto max-w-7xl px-6 lg:px-10">
          <div className="max-w-3xl">
            <p className="text-sm font-semibold uppercase tracking-[0.2em] text-sky-400">
              Demo Gallery
            </p>

            <h2 className="mt-4 text-4xl font-bold md:text-5xl">
              See <Insyt360Brand alignment="lower" /> workflows in action.
            </h2>

            <p className="mt-6 text-lg leading-relaxed text-slate-400">
              Product screenshots and examples from the INSYT Demo Docs
              will appear here in a scroll-through gallery.
            </p>
          </div>

          <div className="mt-14">
            <button
              type="button"
              onClick={() =>
                setSelectedScreenshot({
                  src: "/advantage/insyt-summaries.png",
                  alt:
                    "INSYT Summaries document viewer and Summary QC Review workspace",
                  title: "INSYT Summaries",
                })
              }
              className="group block w-full overflow-hidden rounded-3xl border border-slate-700 bg-slate-900 text-left shadow-2xl transition hover:border-sky-500"
            >
              <div className="relative aspect-[16/8] w-full overflow-hidden bg-slate-950">
                <Image
                  src="/advantage/insyt-summaries.png"
                  alt="INSYT Summaries document viewer and Summary QC Review workspace"
                  fill
                  sizes="100vw"
                  className="object-cover object-top transition duration-300 group-hover:scale-[1.01]"
                  priority={false}
                />
              </div>

              <div className="flex flex-col gap-3 border-t border-slate-800 p-6 md:flex-row md:items-center md:justify-between">
                <div>
                  <h3 className="insyt-workspace text-2xl font-bold text-white">
                    INSYT Summaries
                  </h3>

                  <p className="mt-2 text-slate-400">
                    Source-document navigation, structured summary review,
                    and editable QC workflows within one synchronized workspace.
                  </p>
                </div>

                <span className="inline-flex shrink-0 items-center gap-2 font-semibold text-sky-400 transition group-hover:text-sky-300">
                  View Screenshot
                  <ArrowRight size={17} />
                </span>
              </div>
            </button>
          </div>
        </div>
      </section>

      <section
        id="contact"
        className="scroll-mt-24 py-24"
      >
        <div className="mx-auto max-w-7xl px-6 lg:px-10">
          <div className="overflow-hidden rounded-3xl border border-sky-500/20 bg-slate-900">
            <div className="grid gap-10 p-8 md:p-12 lg:grid-cols-[1fr_auto] lg:items-center">
              <div>
                <p className="text-sm font-semibold uppercase tracking-[0.2em] text-sky-400">
                  Contact
                </p>

                <h2 className="mt-4 text-4xl font-bold">
                  Start a conversation about <Insyt360Brand />.
                </h2>

                <p className="mt-5 max-w-3xl text-lg leading-relaxed text-slate-400">
                  Contact INSYT to discuss a demonstration,
                  pilot project, pricing, or a custom{" "}
                  <Insyt360Brand alignment="raise" /> workflow.
                </p>
              </div>

              <div className="flex flex-col gap-3 sm:flex-row lg:flex-col">
                <a
                  href="mailto:info@insyt360.com"
                  className="inline-flex min-w-[210px] items-center justify-center gap-2 rounded-xl bg-sky-500 px-6 py-3.5 font-semibold text-slate-950 transition hover:bg-sky-400"
                >
                  Contact INSYT
                  <ArrowRight size={18} />
                </a>

                <Link
                  href={user ? "/launcher" : "/login"}
                  className="inline-flex min-w-[210px] items-center justify-center rounded-xl border border-slate-700 px-6 py-3.5 font-semibold text-white transition hover:border-sky-500"
                >
                  {user ? "Open Launcher" : "Secure Sign In"}
                </Link>
              </div>
            </div>
          </div>
        </div>
      </section>

      {selectedScreenshot && (
        <div
          className="fixed inset-0 z-[100] flex items-center justify-center bg-slate-950/95 p-4 backdrop-blur-sm md:p-8"
          role="dialog"
          aria-modal="true"
          aria-label={`${selectedScreenshot.title} screenshot`}
          onClick={() => setSelectedScreenshot(null)}
        >
          <div
            className="relative flex max-h-[94vh] w-full max-w-[1700px] flex-col overflow-hidden rounded-3xl border border-slate-700 bg-slate-900 shadow-2xl"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="flex items-center justify-between border-b border-slate-800 px-5 py-4">
              <div>
                <p className="flex items-center gap-1 text-xs font-semibold uppercase tracking-[0.2em] text-sky-400">
                  <Insyt360Brand />
                  <span>Demo</span>
                </p>

                <h2 className="insyt-workspace mt-1 text-xl font-bold text-white md:text-2xl">
                  {selectedScreenshot.title}
                </h2>
              </div>

              <button
                type="button"
                onClick={() => setSelectedScreenshot(null)}
                className="rounded-xl border border-slate-700 bg-slate-950 p-2.5 text-slate-300 transition hover:border-sky-500 hover:text-white"
                aria-label="Close screenshot"
              >
                <X size={22} />
              </button>
            </div>

            <div className="overflow-auto bg-slate-950 p-2 md:p-4">
              <Image
                src={selectedScreenshot.src}
                alt={selectedScreenshot.alt}
                width={1768}
                height={864}
                className="h-auto w-full rounded-xl"
                sizes="100vw"
              />
            </div>
          </div>
        </div>
      )}

      <footer className="border-t border-slate-800 bg-slate-950">
        <div className="mx-auto flex max-w-7xl flex-col gap-6 px-6 py-10 md:flex-row md:items-center md:justify-between lg:px-10">
          <div>
            <div className="flex items-center">
              <Insyt360Brand className="text-3xl font-bold" />
            </div>

            <p className="mt-2 text-sm text-slate-500">
              Enterprise Review & Intelligence Platform
            </p>
          </div>

          <div className="text-sm text-slate-500">
            Powered by Cyber Discovery Solutions
          </div>
        </div>
      </footer>
    </main>
  );
}