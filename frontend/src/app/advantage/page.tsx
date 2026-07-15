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

const products = [
  {
    name: "INSYT Capture",
    description:
      "Protocol-driven cyber incident response workflows for identifying, reviewing, validating, and reporting sensitive information.",
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
    icon: Layers3,
    features: [
      "Concurrent summary review",
      "Human quality-control workflows",
      "Linked source-document navigation",
    ],
    href: "/summaries/projects",
  },
  {
    name: "Cyber² Utility Suite",
    description:
      "Internal data-processing utilities that prepare, normalize, merge, deduplicate, and organize project information.",
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

  function closeMobileMenu() {
    setMobileMenuOpen(false);
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
            className="flex items-end gap-0.5"
            aria-label="Return to INSYT360 Launcher"
          >
            <span className="insyt-brand text-4xl font-bold text-white">
              I
            </span>

            <span className="insyt-brand text-4xl font-bold text-sky-400">
              N
            </span>

            <span className="insyt-brand text-4xl font-bold text-white">
              SYT
            </span>

            <span className="insyt-brand mb-[0.18em] text-[1.45em] font-bold leading-none text-sky-400">
              360
            </span>
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

          <div className="hidden items-center gap-3 md:flex">
            <Link
              href="/launcher"
              className="rounded-xl border border-slate-700 px-4 py-2.5 text-sm font-semibold text-slate-200 transition hover:border-sky-500 hover:text-white"
            >
              Launcher
            </Link>

            <Link
              href={user ? "/launcher" : "/login"}
              className="rounded-xl bg-sky-500 px-5 py-2.5 text-sm font-semibold text-slate-950 transition hover:bg-sky-400"
            >
              {user ? "Open INSYT360" : "Secure Sign In"}
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

              <div className="mt-2 grid grid-cols-2 gap-3">
                <Link
                  href="/launcher"
                  className="rounded-xl border border-slate-700 px-4 py-3 text-center text-sm font-semibold text-slate-200"
                >
                  Launcher
                </Link>

                <Link
                  href={user ? "/launcher" : "/login"}
                  className="rounded-xl bg-sky-500 px-4 py-3 text-center text-sm font-semibold text-slate-950"
                >
                  {user ? "Open INSYT360" : "Sign In"}
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

            <h1 className="insyt-workspace max-w-4xl text-5xl font-bold leading-tight text-white md:text-6xl lg:text-7xl">
              Explore{" "}
              <span className="text-white">I</span>
              <span className="text-sky-400">N</span>
              <span className="text-white">SYT</span>
              <span className="text-sky-400">360</span>
            </h1>

            <p className="mt-7 max-w-3xl text-xl leading-relaxed text-slate-300">
              A unified review and intelligence platform built for
              document-intensive legal, cybersecurity, privacy, and
              investigative workflows.
            </p>

            <p className="mt-5 max-w-3xl text-base leading-relaxed text-slate-400">
              INSYT360 combines structured processing, AI-assisted
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

                <h2 className="insyt-workspace mt-2 text-2xl font-bold">
                  One Platform. Multiple Workflows.
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

                      <p className="mt-1 text-sm text-slate-500">
                        Connected INSYT360 workflow
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
              INSYT360 is designed to reduce disconnected tools, repetitive
              processing, and unnecessary review effort while preserving
              professional oversight and defensible results.
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

                  <Link
                    href={product.href}
                    className="mt-8 inline-flex items-center gap-2 font-semibold text-sky-400 transition hover:text-sky-300"
                  >
                    Open product
                    <ArrowRight size={17} />
                  </Link>
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
              INSYT360 supports flexible pricing based on project volume,
              workflow requirements, platform access, managed services, and
              the level of professional review required.
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

            <h2 className="insyt-workspace mt-4 text-4xl font-bold md:text-5xl">
              See INSYT360 workflows in action.
            </h2>

            <p className="mt-6 text-lg leading-relaxed text-slate-400">
              Product screenshots and examples from the INSYT Demo Docs
              will appear here in a scroll-through gallery.
            </p>
          </div>

          <div className="mt-14 rounded-3xl border border-dashed border-slate-700 bg-slate-900/60 px-8 py-20 text-center">
            <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-2xl border border-sky-500/20 bg-sky-500/10 text-sky-400">
              <Layers3 size={30} />
            </div>

            <h3 className="insyt-workspace mt-6 text-2xl font-bold">
              Demo screenshots coming next
            </h3>

            <p className="mx-auto mt-4 max-w-2xl leading-relaxed text-slate-400">
              This section is ready for the Capture, Discovery, Summaries,
              and Cyber² screenshots selected from the Demo Docs.
            </p>
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

                <h2 className="insyt-workspace mt-4 text-4xl font-bold">
                  Start a conversation about INSYT360.
                </h2>

                <p className="mt-5 max-w-3xl text-lg leading-relaxed text-slate-400">
                  Contact Cyber Discovery Solutions to discuss a
                  demonstration, pilot project, pricing, or a custom
                  INSYT360 workflow.
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

      <footer className="border-t border-slate-800 bg-slate-950">
        <div className="mx-auto flex max-w-7xl flex-col gap-6 px-6 py-10 md:flex-row md:items-center md:justify-between lg:px-10">
          <div>
            <div className="flex items-end gap-0.5">
              <span className="insyt-brand text-3xl font-bold text-white">
                I
              </span>

              <span className="insyt-brand text-3xl font-bold text-sky-400">
                N
              </span>

              <span className="insyt-brand text-3xl font-bold text-white">
                SYT
              </span>

              <span className="insyt-brand mb-[0.2em] text-[1.15em] font-bold leading-none text-sky-400">
                360
              </span>
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