import React from "react";
import { Link } from "react-router-dom";
import supabase from "../utils/supabaseClient";
import cheeseBoard from "./sponsoredby/cheese_board.png";
import community from "./sponsoredby/community.png";
import farm from "./sponsoredby/farm.png";
import feedingElmeda from "./sponsoredby/feeding_elmeda.png";
import feelGoodBakery from "./sponsoredby/feel_good_backery.png";
import shareChicken from "./sponsoredby/sharechicken.png";
import sharePizza from "./sponsoredby/sharepizza.png";
import aclc from "./sponsoredby/ACLC.jpg";
import allGoodLiving from "./sponsoredby/allgoodliving.jpg";
import island from "./sponsoredby/island.jpg";
import jets from "./sponsoredby/jets.jpg";
import ruby from "./sponsoredby/Ruby.jpg";
import theAcademy from "./sponsoredby/the academy.jpg";
import foodrecovery from "./sponsoredby/foodrecovery.png";
import foodshift from "./sponsoredby/foodshift.png";

// ─── Local sponsor data — kept untouched so the Supabase merge still works ──
const localSponsors = [
  {
    name: "The Cheese Board Collective",
    img: cheeseBoard,
    website: "https://cheeseboardcollective.coop/",
    description: "A worker-owned cooperative bakery and pizzeria in Berkeley since 1971",
    food_saved_from_waste_lb: 2500,
    food_donated_lb: 1800,
  },
  {
    name: "Alameda County Community Food bank",
    img: community,
    website: "https://accfb.org",
    description: "the Alameda County community food Bank is non-profit organization that supplies food to 400+ Alameda County.",
    food_saved_from_waste_lb: 15000,
    food_donated_lb: 12500,
  },
  {
    name: "Semifreddi's",
    img: farm,
    website: "https://www.semifreddis.com/",
    description: "Semifreddi's Bakery is an Alameda-based artisan backery that serves the entire San Francisco Bay Area.",
    food_saved_from_waste_lb: 3200,
    food_donated_lb: 2900,
  },
  {
    name: "Alameda Food Bank",
    img: feedingElmeda,
    website: "https://www.alamedafoodbank.org/",
    description: "Founded in 1977, the Alameda Food Bank is a non-profit organization that helps Alameda community by providing nourishing food to those in need.",
    food_saved_from_waste_lb: 8500,
    food_donated_lb: 7200,
  },
  {
    name: "Community Kitchen",
    img: shareChicken,
    website: "https://www.ckoakland.org/",
    description: "Community Kichen's mission is to harness the power of food to change lives, uplift communities and protect our enviroment.",
    food_saved_from_waste_lb: 4500,
    food_donated_lb: 4100,
  },
  {
    name: "Berkeley Pizza Collective",
    img: sharePizza,
    website: "https://www.sharepizzakitchen.com",
    description: "We specialize in sourdough pizza with craft that is crispy on outside, soft on the inside, and taste like sourdough when you bite into it",
    food_saved_from_waste_lb: 1200,
    food_donated_lb: 950,
  },
  {
    name: "Food shift",
    img: foodshift,
    website: "https://foodshift.net",
    description: "At Food Shift, we transform surplus into opportunities. Since 2012, we've been reducing food waste and nourishing neighbors in the San Francisco Bay Area while sharing solutions globally. Together, we're building a stronger, more equitable food system",
    food_saved_from_waste_lb: 18500,
    food_donated_lb: 16200,
  },
  {
    name: "Food recovery",
    img: foodrecovery,
    website: "https//foodrecovery.org",
    description: "We connect food donors with nonprofits to fight hunger and reduce waste. Our solutions make it easy to donate or receive food while helping the environment. All for free.",
    food_saved_from_waste_lb: 22000,
    food_donated_lb: 19500,
  },
  {
    name: "Trybe Inc.",
    img: null,
    website: "https://www.trybeinc.org",
    description: "Trybe Inc. is a community-based non-profit rooted in Oakland's Eastlake/San Antonio/Fruitvale area, serving youth, young adults, and families in Oakland, Berkeley, Richmond, Hayward and the greater East Bay Area.",
    food_saved_from_waste_lb: 0,
    food_donated_lb: 0,
  },
];

// ───────────────────────── Helpers ───────────────────────────────────────

/** Respects `prefers-reduced-motion` so we don't ship motion to people who opt out. */
function useReducedMotion() {
  const [reduced, setReduced] = React.useState(false);
  React.useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia) return;
    const mql = window.matchMedia("(prefers-reduced-motion: reduce)");
    const onChange = () => setReduced(!!mql.matches);
    onChange();
    mql.addEventListener?.("change", onChange);
    return () => mql.removeEventListener?.("change", onChange);
  }, []);
  return reduced;
}

/** Animated count-up that only runs when the element is in view. */
function CountUp({ value = 0, duration = 1400, format = (n) => n.toLocaleString(), className = "" }) {
  const reduced = useReducedMotion();
  const [display, setDisplay] = React.useState(reduced ? value : 0);
  const ref = React.useRef(null);
  const startedRef = React.useRef(false);

  React.useEffect(() => {
    if (reduced) {
      setDisplay(value);
      return;
    }
    if (!ref.current || startedRef.current) return;
    const el = ref.current;
    const io = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting) && !startedRef.current) {
          startedRef.current = true;
          const start = performance.now();
          const from = 0;
          const to = Number(value) || 0;
          const tick = (now) => {
            const t = Math.min(1, (now - start) / duration);
            // ease-out cubic
            const eased = 1 - Math.pow(1 - t, 3);
            setDisplay(Math.round(from + (to - from) * eased));
            if (t < 1) requestAnimationFrame(tick);
          };
          requestAnimationFrame(tick);
          io.disconnect();
        }
      },
      { threshold: 0.2 }
    );
    io.observe(el);
    return () => io.disconnect();
  }, [value, duration, reduced]);

  return (
    <span ref={ref} className={className}>
      {format(display)}
    </span>
  );
}

/**
 * Infer a category from a sponsor's name when the DB doesn't supply one.
 * Used for visual categorization (badge color + icon) and the filter chips.
 */
function inferCategory(sponsor) {
  if (sponsor.category) return sponsor.category;
  const text = `${sponsor.name || ""} ${sponsor.description || ""}`.toLowerCase();
  if (/bakery|bread|pizza|cheese|kitchen/.test(text)) return "Bakery & Kitchen";
  if (/food bank|community food|pantry/.test(text)) return "Food Bank";
  if (/recovery|recover|shift|surplus|waste/.test(text)) return "Food Recovery";
  if (/farm|produce|grocer/.test(text)) return "Farm & Producer";
  if (/youth|community|family|inc\.?$|non[- ]?profit/.test(text)) return "Community";
  return "Partner";
}

const CATEGORY_TOKENS = {
  "Bakery & Kitchen": { icon: "fa-bread-slice", chip: "bg-amber-50 text-amber-700 ring-amber-200" },
  "Food Bank":        { icon: "fa-warehouse",   chip: "bg-blue-50 text-blue-700 ring-blue-200" },
  "Food Recovery":    { icon: "fa-recycle",     chip: "bg-emerald-50 text-emerald-700 ring-emerald-200" },
  "Farm & Producer":  { icon: "fa-seedling",    chip: "bg-lime-50 text-lime-700 ring-lime-200" },
  "Community":        { icon: "fa-people-group", chip: "bg-rose-50 text-rose-700 ring-rose-200" },
  "Partner":          { icon: "fa-handshake",   chip: "bg-slate-50 text-slate-700 ring-slate-200" },
};

// USDA: ~1.2 lbs of food ≈ 1 meal. EPA: ~3.6 lbs CO2-e per lb of food waste prevented.
const MEALS_PER_LB = 1 / 1.2;
const CO2E_PER_LB = 3.6;

const lbsToMeals = (lbs) => Math.round(lbs * MEALS_PER_LB);
const lbsToKgCO2 = (lbs) => Math.round(lbs * CO2E_PER_LB * 0.4535924); // lb → kg

// ───────────────────────── Sub-components ────────────────────────────────

function SkeletonCard() {
  return (
    <div className="bg-white rounded-2xl border border-gray-100 shadow-sm overflow-hidden">
      <div className="h-44 bg-gradient-to-br from-gray-100 to-gray-200 animate-pulse" />
      <div className="p-6 space-y-3">
        <div className="h-5 w-2/3 bg-gray-200 rounded animate-pulse" />
        <div className="h-3 w-full bg-gray-200 rounded animate-pulse" />
        <div className="h-3 w-5/6 bg-gray-200 rounded animate-pulse" />
        <div className="grid grid-cols-2 gap-2 mt-3">
          <div className="h-14 bg-gray-100 rounded-lg animate-pulse" />
          <div className="h-14 bg-gray-100 rounded-lg animate-pulse" />
        </div>
        <div className="h-9 bg-gray-100 rounded-lg animate-pulse mt-2" />
      </div>
    </div>
  );
}

function StatCard({ icon, iconColor, iconBg, value, label, equivalent }) {
  return (
    <div className="group relative bg-white rounded-2xl border border-gray-100 shadow-sm hover:shadow-md transition-shadow p-6 overflow-hidden">
      {/* Soft decorative blob in the top-right */}
      <div className={`absolute -top-10 -right-10 w-32 h-32 rounded-full opacity-40 blur-2xl ${iconBg}`} aria-hidden="true" />
      <div className={`relative h-12 w-12 rounded-2xl ${iconBg} ${iconColor} flex items-center justify-center mb-4 ring-1 ring-inset ring-white/40`}>
        <i className={`fas ${icon} text-lg`} aria-hidden="true" />
      </div>
      <p className="relative text-3xl sm:text-4xl font-bold text-gray-900 tabular-nums leading-none">
        {value}
      </p>
      <p className="relative text-sm text-gray-600 mt-1.5">{label}</p>
      {equivalent && (
        <p className="relative text-[11px] text-gray-500 mt-2 flex items-center gap-1">
          <i className="fas fa-equals text-[8px] text-gray-400" aria-hidden="true" />
          <span>{equivalent}</span>
        </p>
      )}
    </div>
  );
}

function SponsorCard({ sponsor, totalSaved, isFeatured = false }) {
  const foodSavedValue = Math.round(sponsor.food_saved_from_waste_lb || 0);
  const foodDonatedValue = Math.round(sponsor.food_donated_lb || 0);
  const hasMetrics = foodSavedValue > 0 || foodDonatedValue > 0;
  const sharePct = totalSaved > 0 ? Math.min(100, (foodSavedValue / totalSaved) * 100) : 0;
  const category = inferCategory(sponsor);
  const tokens = CATEGORY_TOKENS[category] || CATEGORY_TOKENS.Partner;
  const initials = (sponsor.name || "?")
    .split(/[\s&]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((s) => s[0]?.toUpperCase())
    .join("");

  return (
    <article
      className={`group relative bg-white rounded-2xl border shadow-sm hover:shadow-xl hover:-translate-y-1 transition-all duration-300 overflow-hidden flex flex-col focus-within:ring-2 focus-within:ring-[#2CABE3]/40 ${
        isFeatured ? "border-amber-200/80 shadow-amber-100" : "border-gray-100"
      }`}
    >
      {isFeatured && (
        <span className="absolute top-3 right-3 z-10 inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-gradient-to-r from-amber-400 to-orange-400 text-white text-[10px] font-semibold uppercase tracking-wider shadow-md">
          <i className="fas fa-crown text-[9px]" aria-hidden="true" /> Top
        </span>
      )}

      {/* Logo area */}
      <div className="relative h-44 bg-gradient-to-br from-gray-50 to-gray-100 flex items-center justify-center p-6">
        {sponsor.img ? (
          <img
            src={sponsor.img}
            alt={`${sponsor.name} logo`}
            loading="lazy"
            className="max-h-full max-w-full object-contain transition-transform duration-500 group-hover:scale-105"
          />
        ) : (
          <div className="flex flex-col items-center justify-center">
            <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-[#2CABE3]/15 to-emerald-100 flex items-center justify-center text-[#2CABE3] font-bold text-xl mb-2 ring-1 ring-[#2CABE3]/20">
              {initials || <i className="fas fa-building text-2xl" aria-hidden="true" />}
            </div>
            <span className="text-xs font-medium text-gray-500 text-center px-2">{sponsor.name}</span>
          </div>
        )}

        {/* Category chip */}
        <span
          className={`absolute top-3 left-3 inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-white/95 ring-1 text-[10px] font-semibold uppercase tracking-wide shadow-sm ${tokens.chip}`}
        >
          <i className={`fas ${tokens.icon} text-[9px]`} aria-hidden="true" />
          {category}
        </span>
      </div>

      {/* Body */}
      <div className="p-6 flex flex-col flex-1">
        <h3 className="text-lg font-semibold text-gray-900 mb-2 leading-tight">{sponsor.name}</h3>
        <p className="text-gray-600 text-sm mb-4 line-clamp-3">{sponsor.description}</p>

        {hasMetrics ? (
          <>
            <div className="grid grid-cols-2 gap-2 mb-3">
              <div className="bg-emerald-50 rounded-lg p-3 text-center ring-1 ring-emerald-100">
                <div className="flex items-center justify-center text-emerald-700 mb-1">
                  <i className="fas fa-leaf mr-1 text-[10px]" aria-hidden="true" />
                  <span className="text-[10px] font-semibold uppercase tracking-wide">Saved</span>
                </div>
                <p className="text-base font-bold text-gray-900 tabular-nums">
                  <CountUp value={foodSavedValue} />
                  <span className="text-xs font-normal text-gray-500"> lb</span>
                </p>
              </div>
              <div className="bg-blue-50 rounded-lg p-3 text-center ring-1 ring-blue-100">
                <div className="flex items-center justify-center text-[#2CABE3] mb-1">
                  <i className="fas fa-hands-helping mr-1 text-[10px]" aria-hidden="true" />
                  <span className="text-[10px] font-semibold uppercase tracking-wide">Donated</span>
                </div>
                <p className="text-base font-bold text-gray-900 tabular-nums">
                  <CountUp value={foodDonatedValue} />
                  <span className="text-xs font-normal text-gray-500"> lb</span>
                </p>
              </div>
            </div>

            {/* Share-of-impact bar — visually compares this sponsor to the rest */}
            {sharePct > 0 && (
              <div className="mb-4">
                <div className="flex items-center justify-between text-[10px] text-gray-500 mb-1">
                  <span className="uppercase tracking-wide font-medium">Share of impact</span>
                  <span className="tabular-nums font-semibold text-gray-700">{sharePct.toFixed(1)}%</span>
                </div>
                <div
                  className="h-1.5 w-full rounded-full bg-gray-100 overflow-hidden"
                  role="progressbar"
                  aria-valuenow={Math.round(sharePct)}
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-label={`${sponsor.name} contributes ${sharePct.toFixed(1)} percent of total saved food`}
                >
                  <div
                    className="h-full bg-gradient-to-r from-emerald-400 to-[#2CABE3] rounded-full transition-all duration-700"
                    style={{ width: `${sharePct}%` }}
                  />
                </div>
              </div>
            )}
          </>
        ) : (
          <div className="mb-4 px-3 py-2.5 rounded-lg bg-amber-50 ring-1 ring-amber-100 flex items-center gap-2 text-[11px] text-amber-800">
            <i className="fas fa-clock text-amber-600" aria-hidden="true" />
            <span>New partner — first metrics coming soon.</span>
          </div>
        )}

        <div className="mt-auto">
          {sponsor.website && sponsor.website !== "#" ? (
            <a
              href={sponsor.website}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center justify-center w-full px-4 py-2.5 rounded-lg bg-[#2CABE3]/10 text-[#2CABE3] hover:bg-[#2CABE3] hover:text-white font-medium text-sm transition-colors group/btn"
              aria-label={`Visit ${sponsor.name} website (opens in new tab)`}
            >
              Visit website
              <i className="fas fa-arrow-up-right-from-square ml-2 text-[10px] transition-transform group-hover/btn:translate-x-0.5 group-hover/btn:-translate-y-0.5" aria-hidden="true" />
            </a>
          ) : (
            <span className="block text-center text-gray-400 text-sm py-2">
              Website coming soon
            </span>
          )}
        </div>
      </div>
    </article>
  );
}

// ───────────────────────── Page ──────────────────────────────────────────

function SponsorsPage() {
  const [sponsors, setSponsors] = React.useState([]);
  const [loading, setLoading] = React.useState(true);
  const [search, setSearch] = React.useState("");
  const [sortBy, setSortBy] = React.useState("impact"); // 'impact' | 'name' | 'newest'
  const [activeCategory, setActiveCategory] = React.useState("All");

  React.useEffect(() => {
    let cancelled = false;
    const run = async () => {
      try {
        const { data, error } = await supabase
          .from("sponsors")
          .select("*")
          .eq("is_active", true)
          .order("display_order", { ascending: true });
        if (error) throw error;

        let merged;
        if (data && data.length > 0) {
          merged = data.map((dbSponsor) => {
            const localSponsor = localSponsors.find((s) => s.name === dbSponsor.name);
            return {
              ...dbSponsor,
              img: localSponsor?.img || dbSponsor.logo_url,
              description: dbSponsor.description || localSponsor?.description || "",
              website: dbSponsor.website || localSponsor?.website || "",
              food_saved_from_waste_lb: parseFloat(dbSponsor.food_saved_from_waste_lb) || 0,
              food_donated_lb: parseFloat(dbSponsor.food_donated_lb) || 0,
            };
          });
        } else {
          merged = localSponsors;
        }
        if (!cancelled) setSponsors(merged);
      } catch (err) {
        console.error("Error fetching sponsors:", err);
        if (!cancelled) setSponsors(localSponsors);
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    run();
    return () => {
      cancelled = true;
    };
  }, []);

  // Aggregate metrics — memoized so re-renders from search input don't recompute.
  const totals = React.useMemo(() => {
    const saved = sponsors.reduce((s, x) => s + (parseFloat(x.food_saved_from_waste_lb) || 0), 0);
    const donated = sponsors.reduce((s, x) => s + (parseFloat(x.food_donated_lb) || 0), 0);
    return { saved, donated, count: sponsors.length };
  }, [sponsors]);

  // Categories actually present — drives the filter chip rail.
  const categories = React.useMemo(() => {
    const seen = new Set(sponsors.map(inferCategory));
    return ["All", ...Array.from(seen)];
  }, [sponsors]);

  // Top contributors get the spotlight treatment (up to 2).
  const topContributors = React.useMemo(() => {
    return [...sponsors]
      .filter((s) => (parseFloat(s.food_saved_from_waste_lb) || 0) > 0)
      .sort((a, b) => (b.food_saved_from_waste_lb || 0) - (a.food_saved_from_waste_lb || 0))
      .slice(0, 2);
  }, [sponsors]);
  const topIds = React.useMemo(() => new Set(topContributors.map((s) => s.id || s.name)), [topContributors]);

  // Filter + sort the visible grid.
  const filteredSponsors = React.useMemo(() => {
    const q = search.trim().toLowerCase();
    const list = sponsors.filter((s) => {
      if (activeCategory !== "All" && inferCategory(s) !== activeCategory) return false;
      if (!q) return true;
      return `${s.name || ""} ${s.description || ""}`.toLowerCase().includes(q);
    });
    if (sortBy === "name") {
      list.sort((a, b) => (a.name || "").localeCompare(b.name || ""));
    } else if (sortBy === "impact") {
      list.sort((a, b) => (b.food_saved_from_waste_lb || 0) - (a.food_saved_from_waste_lb || 0));
    }
    return list;
  }, [sponsors, search, sortBy, activeCategory]);

  const clearFilters = () => {
    setSearch("");
    setActiveCategory("All");
    setSortBy("impact");
  };
  const hasActiveFilters = search.trim() || activeCategory !== "All" || sortBy !== "impact";

  return (
    <div className="min-h-screen bg-gradient-to-b from-[#2CABE3]/5 via-white to-emerald-50/40">
      {/* ───────────── Hero ───────────── */}
      <header className="relative overflow-hidden">
        {/* Decorative gradient blobs */}
        <div className="absolute inset-0 -z-10" aria-hidden="true">
          <div className="absolute -top-24 -left-24 w-96 h-96 rounded-full bg-[#2CABE3]/15 blur-3xl" />
          <div className="absolute top-10 -right-24 w-96 h-96 rounded-full bg-emerald-300/20 blur-3xl" />
        </div>

        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-16 pb-12 sm:pt-20 sm:pb-16">
          <div className="text-center">
            <span className="inline-flex items-center px-3 py-1 rounded-full bg-[#2CABE3]/10 text-[#2CABE3] text-xs font-semibold mb-5 ring-1 ring-[#2CABE3]/20">
              <i className="fas fa-heart mr-2" aria-hidden="true"></i>
              Community Partners
            </span>
            <h1 className="text-4xl sm:text-5xl lg:text-6xl font-bold text-gray-900 mb-5 tracking-tight">
              Together we rescue food,{" "}
              <span className="bg-gradient-to-r from-[#2CABE3] to-emerald-500 bg-clip-text text-transparent">
                not just plates
              </span>
            </h1>
            <p className="text-base sm:text-lg text-gray-600 max-w-2xl mx-auto leading-relaxed">
              These local businesses, food banks, and nonprofits power DoGoods every day.
              Their impact is your community&apos;s impact.
            </p>

            {/* Inline preview pill — gives a flavor of the scale up-front */}
            {!loading && sponsors.length > 0 && (
              <div className="mt-7 flex flex-wrap items-center justify-center gap-2 text-sm">
                <span className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-white shadow-sm ring-1 ring-gray-200 text-gray-700">
                  <i className="fas fa-handshake text-[#2CABE3]" aria-hidden="true" />
                  <strong className="tabular-nums">{totals.count}</strong>
                  <span className="text-gray-500">partners</span>
                </span>
                <span className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-white shadow-sm ring-1 ring-gray-200 text-gray-700">
                  <i className="fas fa-leaf text-emerald-600" aria-hidden="true" />
                  <strong className="tabular-nums">{totals.saved.toLocaleString()}</strong>
                  <span className="text-gray-500">lbs rescued</span>
                </span>
                <a
                  href="#become-sponsor"
                  className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-gradient-to-r from-[#2CABE3] to-emerald-500 text-white font-medium shadow-md hover:shadow-lg hover:scale-105 transition-all"
                >
                  Become a sponsor
                  <i className="fas fa-arrow-down text-[10px]" aria-hidden="true" />
                </a>
              </div>
            )}
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pb-20">
        {/* ───────────── Aggregate impact ───────────── */}
        {!loading && sponsors.length > 0 && (
          <section
            aria-labelledby="impact-heading"
            className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-12"
          >
            <h2 id="impact-heading" className="sr-only">Aggregate impact</h2>
            <StatCard
              icon="fa-leaf"
              iconColor="text-emerald-600"
              iconBg="bg-emerald-100"
              value={<CountUp value={Math.round(totals.saved)} />}
              label="lbs of food saved from waste"
              equivalent={`${lbsToKgCO2(totals.saved).toLocaleString()} kg of CO₂ avoided`}
            />
            <StatCard
              icon="fa-hands-helping"
              iconColor="text-[#2CABE3]"
              iconBg="bg-blue-100"
              value={<CountUp value={Math.round(totals.donated)} />}
              label="lbs of food donated"
              equivalent={`≈ ${lbsToMeals(totals.donated).toLocaleString()} meals served`}
            />
            <StatCard
              icon="fa-handshake"
              iconColor="text-rose-600"
              iconBg="bg-rose-100"
              value={<CountUp value={totals.count} />}
              label="community partners"
              equivalent={`${categories.length - 1} different sectors represented`}
            />
          </section>
        )}

        {/* ───────────── Filter / sort bar ───────────── */}
        {!loading && sponsors.length > 0 && (
          <section
            aria-label="Filter and sort sponsors"
            className="sticky top-0 z-20 -mx-4 sm:mx-0 px-4 sm:px-0 mb-6 py-3 bg-gradient-to-b from-white/95 to-white/85 backdrop-blur-md border-b border-gray-200/60 sm:rounded-2xl sm:border sm:shadow-sm"
          >
            <div className="flex flex-col gap-3">
              {/* Search + sort row */}
              <div className="flex flex-col sm:flex-row gap-3 sm:items-center">
                <div className="relative flex-1">
                  <i
                    className="fas fa-magnifying-glass absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 text-sm"
                    aria-hidden="true"
                  />
                  <input
                    type="search"
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    placeholder="Search sponsors by name or focus…"
                    className="w-full pl-9 pr-9 py-2.5 text-sm rounded-xl border border-gray-200 bg-white text-gray-900 placeholder-gray-400 focus:border-[#2CABE3] focus:ring-2 focus:ring-[#2CABE3]/20 outline-none transition"
                    aria-label="Search sponsors"
                  />
                  {search && (
                    <button
                      type="button"
                      onClick={() => setSearch("")}
                      className="absolute right-2 top-1/2 -translate-y-1/2 w-6 h-6 rounded-full text-gray-400 hover:text-gray-600 hover:bg-gray-100 flex items-center justify-center transition"
                      aria-label="Clear search"
                    >
                      <i className="fas fa-xmark text-xs" aria-hidden="true" />
                    </button>
                  )}
                </div>

                <div className="flex items-center gap-2">
                  <label htmlFor="sort-select" className="text-xs font-medium text-gray-500 uppercase tracking-wide whitespace-nowrap">
                    Sort by
                  </label>
                  <div className="relative">
                    <select
                      id="sort-select"
                      value={sortBy}
                      onChange={(e) => setSortBy(e.target.value)}
                      className="appearance-none pl-3 pr-8 py-2 text-sm rounded-lg border border-gray-200 bg-white text-gray-900 hover:border-gray-300 focus:border-[#2CABE3] focus:ring-2 focus:ring-[#2CABE3]/20 outline-none cursor-pointer"
                    >
                      <option value="impact">Highest impact</option>
                      <option value="name">Name (A–Z)</option>
                    </select>
                    <i
                      className="fas fa-chevron-down absolute right-2.5 top-1/2 -translate-y-1/2 text-[10px] text-gray-400 pointer-events-none"
                      aria-hidden="true"
                    />
                  </div>
                </div>
              </div>

              {/* Category filter chips */}
              {categories.length > 2 && (
                <div className="flex items-center gap-1.5 overflow-x-auto pb-1 -mx-1 px-1" role="tablist">
                  {categories.map((cat) => {
                    const isActive = activeCategory === cat;
                    const tokens = CATEGORY_TOKENS[cat];
                    return (
                      <button
                        key={cat}
                        role="tab"
                        aria-selected={isActive}
                        onClick={() => setActiveCategory(cat)}
                        className={`whitespace-nowrap inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium transition-all border ${
                          isActive
                            ? "bg-[#2CABE3] text-white border-[#2CABE3] shadow-sm"
                            : "bg-white text-gray-700 border-gray-200 hover:border-[#2CABE3]/40 hover:text-[#2CABE3]"
                        }`}
                      >
                        {tokens?.icon && <i className={`fas ${tokens.icon} text-[10px]`} aria-hidden="true" />}
                        {cat}
                      </button>
                    );
                  })}
                  {hasActiveFilters && (
                    <button
                      type="button"
                      onClick={clearFilters}
                      className="ml-auto whitespace-nowrap inline-flex items-center gap-1 px-3 py-1.5 rounded-full text-xs font-medium text-gray-500 hover:text-rose-600 hover:bg-rose-50 transition"
                    >
                      <i className="fas fa-arrow-rotate-left text-[10px]" aria-hidden="true" />
                      Reset
                    </button>
                  )}
                </div>
              )}
            </div>
          </section>
        )}

        {/* ───────────── Grid / loading / empty ───────────── */}
        {loading ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6" aria-busy="true" aria-label="Loading sponsors">
            {Array.from({ length: 6 }).map((_, i) => (
              <SkeletonCard key={i} />
            ))}
          </div>
        ) : filteredSponsors.length === 0 ? (
          <div className="text-center py-16">
            <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-gray-100 text-gray-400 mb-4">
              <i className="fas fa-magnifying-glass text-2xl" aria-hidden="true" />
            </div>
            <h3 className="text-lg font-semibold text-gray-900 mb-1">No partners match those filters</h3>
            <p className="text-sm text-gray-500 mb-5">Try a different search or clear the filters.</p>
            <button
              type="button"
              onClick={clearFilters}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-[#2CABE3] text-white text-sm font-medium hover:bg-[#2CABE3]/90 transition"
            >
              <i className="fas fa-arrow-rotate-left text-xs" aria-hidden="true" />
              Reset filters
            </button>
          </div>
        ) : (
          <>
            {/* Result count for clarity when filtered */}
            <p className="text-xs text-gray-500 mb-4">
              Showing{" "}
              <strong className="text-gray-700 tabular-nums">{filteredSponsors.length}</strong>{" "}
              of {sponsors.length}{" "}
              {sponsors.length === 1 ? "partner" : "partners"}
              {activeCategory !== "All" && (
                <>
                  {" "}in <span className="text-gray-700">{activeCategory}</span>
                </>
              )}
            </p>

            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
              {filteredSponsors.map((sponsor) => (
                <SponsorCard
                  key={sponsor.id || sponsor.name}
                  sponsor={sponsor}
                  totalSaved={totals.saved}
                  isFeatured={topIds.has(sponsor.id || sponsor.name)}
                />
              ))}
            </div>
          </>
        )}

        {/* ───────────── Become a sponsor CTA ───────────── */}
        <section
          id="become-sponsor"
          aria-labelledby="become-sponsor-heading"
          className="mt-20 scroll-mt-8"
        >
          <div className="relative rounded-3xl overflow-hidden shadow-xl">
            {/* Background */}
            <div className="absolute inset-0 bg-gradient-to-br from-[#2CABE3] via-[#2CABE3] to-emerald-500" aria-hidden="true" />
            <div className="absolute inset-0 opacity-30" aria-hidden="true" style={{
              backgroundImage:
                "radial-gradient(circle at 20% 20%, rgba(255,255,255,0.18) 0, transparent 40%), radial-gradient(circle at 80% 60%, rgba(255,255,255,0.12) 0, transparent 40%)",
            }} />

            <div className="relative p-8 sm:p-12 text-white">
              <div className="grid lg:grid-cols-2 gap-8 lg:gap-12 items-center">
                <div>
                  <span className="inline-flex items-center px-3 py-1 rounded-full bg-white/20 text-white text-[11px] font-semibold mb-4 backdrop-blur-sm ring-1 ring-white/30">
                    <i className="fas fa-sparkles mr-2 text-[10px]" aria-hidden="true" />
                    Now welcoming new partners
                  </span>
                  <h2 id="become-sponsor-heading" className="text-3xl sm:text-4xl font-bold mb-4 leading-tight">
                    Put your brand behind real community impact
                  </h2>
                  <p className="text-white/90 text-base sm:text-lg mb-6 leading-relaxed">
                    Join Bay Area leaders rescuing thousands of pounds of food every month.
                    We&apos;ll help measure, tell, and amplify your impact.
                  </p>
                  <div className="flex flex-wrap items-center gap-3">
                    <Link
                      to="/contact"
                      className="inline-flex items-center bg-white text-[#2CABE3] px-6 py-3 rounded-xl font-semibold hover:bg-gray-50 hover:scale-105 active:scale-95 transition-all duration-200 shadow-lg"
                    >
                      <i className="fas fa-handshake mr-2" aria-hidden="true" />
                      Start the conversation
                    </Link>
                    <a
                      href="mailto:partners@dogoods.app"
                      className="inline-flex items-center gap-2 text-white/95 hover:text-white text-sm font-medium underline-offset-4 hover:underline transition"
                    >
                      <i className="fas fa-envelope" aria-hidden="true" />
                      partners@dogoods.app
                    </a>
                  </div>
                </div>

                {/* Benefit cards */}
                <ul className="grid grid-cols-1 sm:grid-cols-2 gap-3" aria-label="Sponsor benefits">
                  {[
                    { icon: "fa-chart-line", title: "Measured impact", body: "Real-time dashboards with pounds rescued and meals served." },
                    { icon: "fa-bullhorn", title: "Brand visibility", body: "Logo placement here and across community communications." },
                    { icon: "fa-people-arrows", title: "Volunteer programs", body: "Engage your team with hands-on food-rescue events." },
                    { icon: "fa-file-shield", title: "Tax-deductible", body: "Donations routed through our 501(c)(3) partner network." },
                  ].map((b) => (
                    <li key={b.title} className="bg-white/10 backdrop-blur-sm rounded-xl p-4 ring-1 ring-white/20">
                      <div className="flex items-center gap-2 mb-1.5">
                        <span className="inline-flex w-7 h-7 rounded-lg bg-white/20 items-center justify-center text-white">
                          <i className={`fas ${b.icon} text-xs`} aria-hidden="true" />
                        </span>
                        <span className="font-semibold text-sm">{b.title}</span>
                      </div>
                      <p className="text-[12px] text-white/85 leading-relaxed">{b.body}</p>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          </div>
        </section>
      </main>
    </div>
  );
}

export default SponsorsPage;
