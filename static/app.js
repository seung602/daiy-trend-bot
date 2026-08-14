(() => {
  const I18N = {
    ko: {
      eyebrow: "KOREA → EUROPE MARKET MONITOR",
      title: "K-Beauty Trend Intelligence",
      refresh: "새로고침",
      ksignalTitle: "🇰🇷 한국 선행 랭킹",
      ksignalHint: "Olive Young · Glowpick · Hwahae · Zigzag 등 국내 이커머스에서 빠르게 오르는 상품",
      ksEmpty: "아직 K-Signal 데이터가 없습니다. 수집 파이프라인이 돌아간 뒤 표시됩니다.",
      westTitle: "🌍 서구 시장 신호",
      westHint: "TikTok · Amazon · Instagram · YouTube 기준 집계 (참고용 · 일별 검색 로테이션 있음)",
      westEmpty: "서구 트렌드 점수 데이터가 없습니다.",
      footer: "Read-only · 외부 API 호출 없음 · DB 스냅샷 기준",
      allMalls: "전체",
      items: "개 상품",
      score: "종합 점수",
      heat: "뜨는 속도",
      boost: "가속 강도",
      trust: "신호 신뢰도",
      daysSeen: "등장 일수",
      periodDay: "오늘",
      periodWeek: "이번 주",
      periodMonth: "이번 달",
      subtitle: (from, to, period) => {
        if (!to) return "데이터 대기 중";
        if (period === "day") return `기준일 ${to}`;
        return `${from} ~ ${to}`;
      },
    },
    en: {
      eyebrow: "KOREA → EUROPE MARKET MONITOR",
      title: "K-Beauty Trend Intelligence",
      refresh: "Refresh",
      ksignalTitle: "🇰🇷 Korea Upstream Ranking",
      ksignalHint: "Fast-rising products on Olive Young, Glowpick, Hwahae, Zigzag and more",
      ksEmpty: "No K-Signal data yet. It appears after the collector pipeline runs.",
      westTitle: "🌍 Western Market Signals",
      westHint: "From TikTok · Amazon · Instagram · YouTube (directional — daily query rotation)",
      westEmpty: "No Western trend scores available.",
      footer: "Read-only · no external API calls · DB snapshot",
      allMalls: "All",
      items: "products",
      score: "Score",
      heat: "Rising speed",
      boost: "Acceleration",
      trust: "Signal strength",
      daysSeen: "Days seen",
      periodDay: "Today",
      periodWeek: "This week",
      periodMonth: "This month",
      subtitle: (from, to, period) => {
        if (!to) return "Waiting for data";
        if (period === "day") return `As of ${to}`;
        return `${from} → ${to}`;
      },
    },
    ar: {
      eyebrow: "KOREA → EUROPE MARKET MONITOR",
      title: "K-Beauty Trend Intelligence",
      refresh: "تحديث",
      ksignalTitle: "🇰🇷 ترتيب كوريا (إشارة مبكرة)",
      ksignalHint: "منتجات سريعة الصعود في Olive Young وGlowpick وHwahae وZigzag",
      ksEmpty: "لا توجد بيانات K-Signal بعد.",
      westTitle: "🌍 إشارات السوق الغربي",
      westHint: "من TikTok وAmazon وInstagram وYouTube",
      westEmpty: "لا توجد درجات اتجاه غربية.",
      footer: "للقراءة فقط · بدون استدعاءات API خارجية",
      allMalls: "الكل",
      items: "منتج",
      score: "النقاط",
      heat: "سرعة الصعود",
      boost: "التسارع",
      trust: "قوة الإشارة",
      daysSeen: "أيام الظهور",
      periodDay: "اليوم",
      periodWeek: "هذا الأسبوع",
      periodMonth: "هذا الشهر",
      subtitle: (from, to, period) => {
        if (!to) return "في انتظار البيانات";
        if (period === "day") return `حتى ${to}`;
        return `${from} → ${to}`;
      },
    },
  };

  let lang = localStorage.getItem("kbeauty_lang") || "ko";
  let period = localStorage.getItem("kbeauty_period") || "day";
  let ksItems = [];
  let activeMall = "all";
  let lastMalls = [];

  const $ = (id) => document.getElementById(id);

  function pack() {
    return I18N[lang] || I18N.ko;
  }

  function t(key) {
    const val = pack()[key];
    return typeof val === "string" ? val : key;
  }

  function applyI18n() {
    document.documentElement.lang = lang;
    document.documentElement.dir = lang === "ar" ? "rtl" : "ltr";
    document.querySelectorAll("[data-i18n]").forEach((el) => {
      const key = el.getAttribute("data-i18n");
      const val = pack()[key];
      if (typeof val === "string") el.textContent = val;
    });
    $("language").value = lang;
    document.querySelectorAll(".period-tab").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.period === period);
    });
  }

  function fmt(n, digits = 1) {
    if (n === null || n === undefined || Number.isNaN(n)) return "—";
    return Number(n).toFixed(digits);
  }

  function mallLabel(mall) {
    if (!mall) return "—";
    return lang === "ko" ? mall.name_ko || mall.name_en : mall.name_en || mall.name_ko;
  }

  function renderMallFilters(malls) {
    lastMalls = malls || [];
    const row = $("mallFilters");
    row.innerHTML = "";
    const all = document.createElement("button");
    all.type = "button";
    all.className = "chip" + (activeMall === "all" ? " active" : "");
    all.textContent = t("allMalls");
    all.onclick = () => {
      activeMall = "all";
      renderKsList();
      renderMallFilters(lastMalls);
    };
    row.appendChild(all);

    lastMalls.forEach((m) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "chip" + (activeMall === m.id ? " active" : "");
      btn.textContent = `${mallLabel(m)} (${m.count})`;
      btn.onclick = () => {
        activeMall = m.id;
        renderKsList();
        renderMallFilters(lastMalls);
      };
      row.appendChild(btn);
    });
  }

  function renderKsList() {
    const list = $("ksList");
    const empty = $("ksEmpty");
    list.innerHTML = "";

    const filtered =
      activeMall === "all"
        ? ksItems
        : ksItems.filter((it) => it.mall && it.mall.id === activeMall);

    if (!filtered.length) {
      empty.classList.remove("hidden");
      return;
    }
    empty.classList.add("hidden");

    filtered.forEach((it) => {
      const card = document.createElement("article");
      card.className = "ks-card";

      const rank = document.createElement("div");
      rank.className = "ks-rank" + (it.rank <= 3 ? " top3" : "");
      rank.textContent = it.rank;

      const body = document.createElement("div");
      body.className = "ks-body";

      const name = document.createElement("h3");
      name.className = "ks-name";
      if (it.url) {
        const a = document.createElement("a");
        a.href = it.url;
        a.target = "_blank";
        a.rel = "noopener noreferrer";
        a.textContent = it.product_name;
        name.appendChild(a);
      } else {
        name.textContent = it.product_name;
      }

      const tags = document.createElement("div");
      tags.className = "ks-tags";

      const mallTag = document.createElement("span");
      mallTag.className = "tag mall";
      mallTag.textContent = mallLabel(it.mall);
      tags.appendChild(mallTag);

      if (it.velocity != null) {
        const v = document.createElement("span");
        v.className = "tag vel";
        v.textContent = `${t("heat")} ${fmt(it.velocity)}`;
        tags.appendChild(v);
      }
      if (it.accel != null) {
        const a = document.createElement("span");
        a.className = "tag vel";
        a.textContent = `${t("boost")} ${fmt(it.accel)}`;
        tags.appendChild(a);
      }
      if (it.confidence != null) {
        const c = document.createElement("span");
        c.className = "tag conf";
        c.textContent = `${t("trust")} ${fmt(it.confidence, 2)}`;
        tags.appendChild(c);
      }
      if (period !== "day" && it.days_seen) {
        const d = document.createElement("span");
        d.className = "tag days";
        d.textContent = `${t("daysSeen")} ${it.days_seen}`;
        tags.appendChild(d);
      }

      body.appendChild(name);
      body.appendChild(tags);

      const metrics = document.createElement("div");
      metrics.className = "ks-metrics";
      const scoreLabel = document.createElement("span");
      scoreLabel.textContent = t("score");
      const scoreVal = document.createElement("strong");
      scoreVal.textContent = fmt(it.score, 1);
      metrics.appendChild(scoreLabel);
      metrics.appendChild(scoreVal);

      card.appendChild(rank);
      card.appendChild(body);
      card.appendChild(metrics);
      list.appendChild(card);
    });
  }

  const PLATFORM_LABEL = {
    tiktok: "TikTok",
    amazon: "Amazon",
    instagram: "Instagram",
    youtube: "YouTube",
    google: "Google",
    k_signal: "K-Signal",
  };

  function renderWest(trends, date) {
    const list = $("westList");
    const empty = $("westEmpty");
    list.innerHTML = "";
    $("westDate").textContent = date || "—";

    if (!trends || !trends.length) {
      empty.classList.remove("hidden");
      return;
    }
    empty.classList.add("hidden");

    const maxScore = Math.max(...trends.map((x) => Number(x.trend_score) || 0), 1);

    trends.slice(0, 20).forEach((row, idx) => {
      const el = document.createElement("article");
      el.className = "west-row";

      const rank = document.createElement("div");
      rank.className = "west-rank";
      rank.textContent = idx + 1;

      const mid = document.createElement("div");
      mid.className = "west-mid";

      const kw = document.createElement("div");
      kw.className = "west-kw";
      kw.textContent = row.keyword;
      mid.appendChild(kw);

      const chips = document.createElement("div");
      chips.className = "plat-chips";
      const platforms = row.platforms || [];
      if (platforms.length) {
        platforms.forEach((p) => {
          const chip = document.createElement("span");
          chip.className = "plat-chip plat-" + String(p).toLowerCase();
          chip.textContent = PLATFORM_LABEL[String(p).toLowerCase()] || p;
          chips.appendChild(chip);
        });
      } else {
        const chip = document.createElement("span");
        chip.className = "plat-chip";
        chip.textContent = "—";
        chips.appendChild(chip);
      }
      mid.appendChild(chips);

      const score = document.createElement("div");
      score.className = "west-score";
      score.textContent = fmt(row.trend_score, 1);

      const bar = document.createElement("div");
      bar.className = "west-bar";
      const fill = document.createElement("span");
      fill.style.width = `${Math.min(100, (Number(row.trend_score) / maxScore) * 100)}%`;
      bar.appendChild(fill);

      el.appendChild(rank);
      el.appendChild(mid);
      el.appendChild(score);
      el.appendChild(bar);
      list.appendChild(el);
    });
  }

  async function loadAll() {
    applyI18n();
    try {
      const [ksRes, trendRes] = await Promise.all([
        fetch(`/api/ksignal/ranking?period=${period}&limit=50`),
        fetch("/api/dashboard/today?limit=20"),
      ]);

      const ks = ksRes.ok
        ? await ksRes.json()
        : { items: [], malls: [], date: null, count: 0, date_from: null, date_to: null };
      let trendsPayload = { trends: [], date: null };
      if (trendRes.ok) trendsPayload = await trendRes.json();

      ksItems = ks.items || [];
      activeMall = "all";

      const rangeLabel =
        period === "day"
          ? ks.date_to || ks.date || "—"
          : ks.date_from && ks.date_to
            ? `${ks.date_from} ~ ${ks.date_to}`
            : ks.date || "—";
      $("ksDate").textContent = rangeLabel;
      $("ksCount").textContent = ks.count ? `${ks.count} ${t("items")}` : "—";
      $("subtitle").textContent = pack().subtitle(
        ks.date_from || ks.date,
        ks.date_to || ks.date,
        period
      );

      renderMallFilters(ks.malls || []);
      renderKsList();
      renderWest(trendsPayload.trends || [], trendsPayload.date);
    } catch (err) {
      console.error(err);
      $("ksEmpty").classList.remove("hidden");
      $("ksEmpty").textContent = String(err.message || err);
    }
  }

  $("language").addEventListener("change", (e) => {
    lang = e.target.value;
    localStorage.setItem("kbeauty_lang", lang);
    applyI18n();
    loadAll();
  });

  $("refreshBtn").addEventListener("click", loadAll);

  document.querySelectorAll(".period-tab").forEach((btn) => {
    btn.addEventListener("click", () => {
      period = btn.dataset.period;
      localStorage.setItem("kbeauty_period", period);
      applyI18n();
      loadAll();
    });
  });

  loadAll();
})();
