// static/js/affiliation.js
(function () {
  // ===================== 공통 설정 =====================
  const cfg = window.affiliationConfig || {};

  const affiliationId   = cfg.id;
  const affiliationName = cfg.name || "";
  const contentType     = cfg.contentType || "affiliation";
  const objectId        = cfg.objectId || affiliationId;
  const pageTitle       = (cfg.pageTitle || "page").trim();
  const csrfToken       = cfg.csrfToken || null;
  const currentPage     = Number(cfg.currentPage || 1);
  const totalPages      = Number(cfg.totalPages || 1);
  const itemsPerPage    = Number(cfg.itemsPerPage || 10);
  const isAuthenticated = String(cfg.isAuthenticated) === "true";

  // ---------------- CSRF / 쿠키 헬퍼 ----------------
  function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== "") {
      const cookies = document.cookie.split(";");
      for (let i = 0; i < cookies.length; i++) {
        const cookie = cookies[i].trim();
        if (cookie.startsWith(name + "=")) {
          cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
          break;
        }
      }
    }
    return cookieValue;
  }

  function getCsrfToken() {
    return csrfToken || getCookie("csrftoken");
  }

  // ===================================================
  // 1. PDF 저장
  // ===================================================
  function initPdfDownload() {
    const btn = document.getElementById("pdfDownload");
    if (!btn) return;

    btn.addEventListener("click", function () {
      const ok = confirm("📄 PDF를 다운로드 하시겠습니까?");
      if (!ok) return;

      const targetElement = document.body;

      html2canvas(targetElement, {
        scale: 2,
        useCORS: true,
        allowTaint: true,
        logging: false,
      })
        .then((canvas) => {
          const imgData = canvas.toDataURL("image/png");

          if (!window.jspdf || !window.jspdf.jsPDF) {
            alert("❌ PDF 라이브러리가 로드되지 않았습니다.");
            return;
          }
          const { jsPDF } = window.jspdf;
          const pdf = new jsPDF("p", "mm", "a4");

          const imgWidth = 210;
          const imgHeight = (canvas.height * imgWidth) / canvas.width;
          pdf.addImage(imgData, "PNG", 0, 0, imgWidth, imgHeight);

          // 파일명 생성
          const safeTitle = pageTitle
            .toLowerCase()
            .replace(/[/\\?%*:|"<>]/g, "") || "page";
          const fileName = `${contentType}_${safeTitle}.pdf`;

          const pdfBlob = pdf.output("blob");
          const formData = new FormData();
          formData.append("pdf", pdfBlob, fileName);
          formData.append("content_type", contentType);
          formData.append("object_id", objectId);
          formData.append("object_title", safeTitle);

          fetch("/affiliation/pdf_upload/", {
            method: "POST",
            headers: {
              "X-CSRFToken": getCsrfToken(),
            },
            body: formData,
          })
            .then((res) =>
              res.json().then((data) => ({
                status: res.status,
                data,
              }))
            )
            .then(({ status, data }) => {
              if (data.success) {
                pdf.save(fileName);
              } else {
                alert("⚠ " + (data.error || "PDF 저장에 실패했습니다."));
                if (status === 403) {
                  window.location.href = "/login/";
                }
              }
            })
            .catch((err) => {
              console.error(err);
              alert("❌ PDF 저장 실패: " + err.message);
            });
        })
        .catch((error) => {
          console.error(error);
          alert("❌ PDF 캡처 실패: " + error.message);
        });
    });
  }

  // ===================================================
  // 2. Chart.js + D3 워드클라우드
  // ===================================================
  // Chart 글로벌 테마
  function setupChartDefaults() {
    if (!window.Chart) return;
    Chart.defaults.font.family =
      "Pretendard, Inter, system-ui, -apple-system, Segoe UI, Roboto, Apple SD Gothic Neo, Noto Sans KR, sans-serif";
    Chart.defaults.color = "#4B4B4B";
    Chart.defaults.plugins.legend.display = false;
    Chart.defaults.plugins.tooltip.cornerRadius = 8;
    Chart.defaults.plugins.tooltip.padding = 10;
    Chart.defaults.animation.duration = 900;
    Chart.defaults.datasets.bar.maxBarThickness = 36;
    Chart.defaults.datasets.bar.borderRadius = 0;
  }

  function hexToRgba(hex, a) {
    const c = hex.replace("#", "");
    const n = parseInt(c, 16);
    return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${a})`;
  }

  function barOpts() {
    return {
      responsive: true,
      maintainAspectRatio: false,
      layout: { padding: { top: 6, right: 8, bottom: 0, left: 0 } },
      scales: {
        x: {
          grid: { display: false },
          ticks: { autoSkip: false, maxRotation: 30, font: { size: 11 } },
        },
        y: {
          beginAtZero: true,
          grid: { color: "rgba(105,0,184,.08)", drawBorder: false },
        },
      },
    };
  }

  function renderBarChart(canvasId, labels, values, color) {
    const el = document.getElementById(canvasId);
    if (!el || !window.Chart) return;
    const ctx = el.getContext("2d");
    return new Chart(ctx, {
      type: "bar",
      data: {
        labels,
        datasets: [
          {
            label: "건수",
            data: values,
            borderWidth: 1,
            borderColor: color,
            backgroundColor: hexToRgba(color, 0.35),
            hoverBackgroundColor: hexToRgba(color, 0.6),
            hoverBorderColor: color,
          },
        ],
      },
      options: barOpts(),
    });
  }

  async function initAffiliationAnalytics() {
    if (!affiliationId) return;
    setupChartDefaults();

    const API_URL = `/affiliation/api/affiliation-analysis/${affiliationId}/`;
    let data;
    try {
      const res = await fetch(API_URL);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      data = await res.json();
    } catch (e) {
      console.error("분석 API 로딩 실패:", e);
      return;
    }

    // 1) 연도별 출판
    const yLabels = Object.keys(data.year_chart_data || {});
    const yValues = Object.values(data.year_chart_data || {});
    renderBarChart("yearChart", yLabels, yValues, "#2E86AB");

    // 2) 파트별 논문
    const pLabels = Object.keys(data.part_chart_data || {});
    const pValues = Object.values(data.part_chart_data || {});
    renderBarChart("partChart", pLabels, pValues, "#F6A01A");

    // 3) 워드클라우드 (d3-cloud, #author-wordcloud 사용)
    if (window.d3 && d3.layout && typeof d3.layout.cloud === "function") {
      const wordsRaw = data.keyword_data || {};
      const MAX_WORDS = 30;
      const words = Object.entries(wordsRaw)
        .sort((a, b) => b[1] - a[1])
        .slice(0, MAX_WORDS)
        .map(([text, size]) => ({ text, size }));

      const svg = d3.select("#author-wordcloud");
      if (!svg.empty()) {
        const box = svg.node().getBoundingClientRect();
        const W = Math.max(300, box.width || 600);
        const H = Math.max(320, box.height || 380);
        const count = words.length;
        const minF = count > 40 ? 12 : count > 25 ? 14 : 16;
        const maxF = count > 40 ? 36 : count > 25 ? 48 : 64;
        const fontScale = d3
          .scaleLinear()
          .domain([d3.min(words, (d) => d.size) || 1, d3.max(words, (d) => d.size) || 10])
          .range([minF, maxF]);

        svg.selectAll("*").remove();

        d3.layout
          .cloud()
          .size([W, H])
          .words(words)
          .padding(Math.max(1, 8 - Math.floor(count / 10)))
          .rotate(() => Math.random() * 30 - 15)
          .fontSize((d) => fontScale(d.size))
          .on("end", (w) => {
            const g = svg.append("g").attr("transform", `translate(${W / 2},${H / 2})`);
            g.selectAll("text")
              .data(w)
              .enter()
              .append("text")
              .style("font-size", (d) => `${d.size}px`)
              .style("fill", (d, i) => d3.schemeCategory10[i % 10])
              .attr("text-anchor", "middle")
              .attr("transform", (d) => `translate(${d.x},${d.y}) rotate(${d.rotate})`)
              .text((d) => d.text)
              .style("cursor", "pointer")
              .on("click", (_, d) => {
                fetch(`/get_keyword_id/?name=${encodeURIComponent(d.text)}`)
                  .then((r) => r.json())
                  .then((j) =>
                    j.keyword_id
                      ? (window.location.href = `/keyword/${j.keyword_id}/`)
                      : alert("해당 키워드 페이지를 찾을 수 없습니다.")
                  );
              });
          })
          .start();
      }
    }
  }

  // ===================================================
  // 3. 공동 기관 네트워크 (instNetworkChart)
  // ===================================================
  function clamp(v, lo, hi) {
    return Math.max(lo, Math.min(hi, v));
  }
  function fitTextInCircle(t, r) {
    const m = r * 1.65;
    const c = Math.max(3, Math.floor(m / 6.5));
    return t.length > c ? t.slice(0, c - 1) + "…" : t;
  }
  function measureText(svg, text, fs, fw, ff) {
    const g = svg
      .append("text")
      .attr("x", -9999)
      .attr("y", -9999)
      .attr("font-size", fs)
      .attr("font-weight", fw)
      .attr("font-family", ff || "inherit")
      .text(text);
    const w = g.node().getBBox().width;
    g.remove();
    return w;
  }
  function edgePointOnRect(cx, cy, ch, hw, hh) {
    const dx = ch.x - cx;
    const dy = ch.y - cy;
    if (!dx && !dy) return { x: cx, y: cy };
    const t = 1 / Math.max(Math.abs(dx) / hw, Math.abs(dy) / hh);
    return { x: cx + dx * t, y: cy + dy * t };
  }

  const PALETTE = {
    main1: "#6B76D6",
    main2: "#B9C3F2",
    stroke: "#4B57BF",
    childFill: "#F3F5FF",
    childStroke: "#C8D0FF",
    linkLow: "#D9DEE8",
    linkHigh: "#3A3F4A",
    hover: "#5E6AED",
  };

  async function renderAffiliationNetwork() {
    if (!affiliationId || !window.d3) return;

    const svg = d3.select("#instNetworkChart").attr("preserveAspectRatio", "xMidYMid meet");
    if (svg.empty()) return;

    let data;
    try {
      const res = await fetch(`/affiliation/api/affiliation-analysis/${affiliationId}/`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      data = await res.json();
    } catch (e) {
      console.error("❌ 네트워크 데이터 로딩 실패:", e);
      return;
    }

    const rawChildren = (data.network_data || []).slice(0, 20).map((d) => ({
      id: d.id,
      name: d.name,
      count: d.count,
      pubs: d.pubs ?? d.publication_count ?? d.paper_count ?? 0,
    }));

    svg.selectAll("*").remove();
    d3.selectAll(".nc-tooltip").remove();

    const box = svg.node().getBoundingClientRect();
    const W = Math.max(560, box.width || 600);
    const H = Math.max(420, box.height || 420);
    svg.attr("viewBox", `0 0 ${W} ${H}`);

    const cx = W / 2;
    const cy = H / 2;

    // gradient
    const defs = svg.append("defs");
    const grad = defs
      .append("linearGradient")
      .attr("id", "ncGradMain")
      .attr("x1", "0%")
      .attr("x2", "100%")
      .attr("y1", "0%")
      .attr("y2", "100%");
    grad.append("stop").attr("offset", "0%").attr("stop-color", PALETTE.main1);
    grad.append("stop").attr("offset", "100%").attr("stop-color", PALETTE.main2);

    const mainFS = 14;
    const mainFW = 600;
    const textW = measureText(svg, affiliationName, mainFS, mainFW);
    const mainW = clamp(textW + 56, 130, W * 0.85);
    const mainH = clamp(mainFS + 32, 50, H * 0.3);

    const nodes = [];
    const mainNode = {
      id: affiliationId,
      name: affiliationName,
      type: "main",
      x: cx,
      y: cy,
      mainW,
      mainH,
    };
    nodes.push(mainNode);

    const counts = rawChildren.map((d) => +d.count);
    const minC = counts.length ? d3.min(counts) : 0;
    const maxC = counts.length ? d3.max(counts) : 1;
    const linkColor = d3
      .scaleLinear()
      .domain([minC, maxC === minC ? minC + 1 : maxC])
      .range([PALETTE.linkLow, PALETTE.linkHigh]);
    const linkWidth = d3
      .scaleLinear()
      .domain([minC, maxC === minC ? minC + 1 : maxC])
      .range([3, 8]);

    const pubs = rawChildren.map((d) => +d.pubs || 0);
    const minP = pubs.length ? d3.min(pubs) : 0;
    const maxP = pubs.length ? d3.max(pubs) : 1;
    const childR = d3
      .scaleSqrt()
      .domain([Math.max(0, minP), Math.max(1, maxP)])
      .range([25, 35]);

    const n = rawChildren.length;
    const step = (2 * Math.PI) / Math.max(1, n);
    const mainHalf = Math.max(mainW, mainH) / 2;
    const canvasHardMax = Math.min(W, H) / 2 - 24;
    const MIN_EDGE_PX = 50;
    const MAX_EDGE_PX = 90;
    const minRing = mainHalf + MIN_EDGE_PX;
    const userMaxR = Math.min(mainHalf + MAX_EDGE_PX, canvasHardMax);
    const span = Math.max(40, userMaxR - minRing);
    const longBase = userMaxR;
    const shortBase = minRing + span * 0.05;
    const jitterA = step * 0.2;
    const randN = d3.randomNormal(0, span * 0.05);
    const fine = () => (Math.random() - 0.5) * 8;
    const inward = d3
      .scaleLinear()
      .domain([minC, maxC || 1])
      .range([0, Math.min(30, span * 0.1)]);

    rawChildren.forEach((d, i) => {
      const a = i * step - Math.PI / 2 + (Math.random() - 0.5) * jitterA;
      let base = i % 2 === 0 ? longBase : shortBase;
      if (i % 4 === 0) base = userMaxR;
      const r = clamp(base + randN() + fine() - inward(d.count || 0), minRing, userMaxR);
      nodes.push({
        id: d.id,
        name: d.name,
        type: "child",
        x: cx + Math.cos(a) * r,
        y: cy + Math.sin(a) * r,
        r: childR(d.pubs || 0),
        count: d.count,
        pubs: d.pubs || 0,
      });
    });

    const links = rawChildren.map((d) => ({
      source: affiliationId,
      target: d.id,
      count: d.count,
    }));

    const gLinks = svg.append("g").attr("class", "nc-links");
    const linkSel = gLinks
      .selectAll("line")
      .data(links)
      .enter()
      .append("line")
      .attr("x1", (d) => {
        const ch = nodes.find((n) => n.id === d.target);
        const p = edgePointOnRect(mainNode.x, mainNode.y, ch, mainW / 2, mainH / 2);
        return p.x;
      })
      .attr("y1", (d) => {
        const ch = nodes.find((n) => n.id === d.target);
        const p = edgePointOnRect(mainNode.x, mainNode.y, ch, mainW / 2, mainH / 2);
        return p.y;
      })
      .attr("x2", (d) => (nodes.find((n) => n.id === d.target) || { x: cx }).x)
      .attr("y2", (d) => (nodes.find((n) => n.id === d.target) || { y: cy }).y)
      .attr("stroke", (d) => linkColor(d.count))
      .attr("stroke-width", (d) => linkWidth(d.count))
      .attr("opacity", 0.95)
      .attr("stroke-linecap", "round");

    const gNodes = svg
      .append("g")
      .attr("class", "nc-nodes")
      .selectAll("g")
      .data(nodes)
      .enter()
      .append("g")
      .attr("transform", (d) => `translate(${d.x},${d.y})`);

    const gMain = gNodes.filter((d) => d.type === "main");
    gMain
      .append("rect")
      .attr("x", (d) => -d.mainW / 2)
      .attr("y", (d) => -d.mainH / 2)
      .attr("width", (d) => d.mainW)
      .attr("height", (d) => d.mainH)
      .attr("rx", 18)
      .attr("fill", "url(#ncGradMain)")
      .attr("stroke", PALETTE.stroke)
      .attr("stroke-width", 3);

    gMain
      .append("text")
      .attr("fill", "#fff")
      .attr("font-weight", 800)
      .attr("text-anchor", "middle")
      .attr("dominant-baseline", "middle")
      .attr("font-size", 14)
      .text((d) => {
        const maxChars = 30;
        return d.name.length > maxChars ? d.name.slice(0, maxChars - 1) + "…" : d.name;
      });

    const gChild = gNodes.filter((d) => d.type === "child");
    gChild
      .append("circle")
      .attr("r", (d) => d.r)
      .attr("fill", PALETTE.childFill)
      .attr("stroke", PALETTE.childStroke)
      .attr("stroke-width", 2)
      .style("cursor", "pointer")
      .on("click", (e, d) => {
        if (d.id) window.location.href = `/affiliation/${d.id}/`;
      })
      .on("mouseenter", function (e, d) {
        d3.select(this).attr("stroke-width", 3).attr("stroke", PALETTE.hover);
        linkSel
          .filter((l) => l.target === d.id)
          .attr("stroke", PALETTE.linkHigh)
          .attr("stroke-width", linkWidth(d.count) + 2);
        tip.html(toolTipHtml(d)).style("display", "block");
      })
      .on("mousemove", (e) => {
        tip.style("left", e.pageX + 12 + "px").style("top", e.pageY - 18 + "px");
      })
      .on("mouseleave", function (e, d) {
        d3.select(this).attr("stroke-width", 2).attr("stroke", PALETTE.childStroke);
        linkSel
          .filter((l) => l.target === d.id)
          .attr("stroke", (l) => linkColor(l.count))
          .attr("stroke-width", (l) => linkWidth(l.count));
        tip.style("display", "none");
      });

    gChild
      .append("text")
      .attr("fill", "#2b2b2b")
      .attr("font-weight", 700)
      .attr("text-anchor", "middle")
      .attr("dominant-baseline", "middle")
      .attr("font-size", "12px")
      .text((d) => fitTextInCircle(d.name, d.r));

    const tip = d3
      .select("body")
      .append("div")
      .attr("class", "nc-tooltip")
      .style("position", "absolute")
      .style("z-index", "9999")
      .style("background", "#111")
      .style("color", "#fff")
      .style("padding", "8px 10px")
      .style("border-radius", "8px")
      .style("box-shadow", "0 6px 16px rgba(0,0,0,.35)")
      .style("font-size", "12px")
      .style("display", "none");

    function toolTipHtml(d) {
      return `
        <div style="font-weight:800;margin-bottom:4px;">${d.name}</div>
        <div>논문 수: <b>${d.pubs}</b></div>
        <div>공동 연구 횟수: <b>${d.count}</b></div>
      `;
    }
  }

  // ===================================================
  // 4. "더보기" 버튼 (저자 목록)
  // ===================================================
  function initToggleAuthors() {
    const btn = document.getElementById("toggleAuthorsBtn");
    const list = document.getElementById("allAuthorsList");
    if (!btn || !list) return;

    btn.addEventListener("click", function () {
      const open = list.style.display !== "block";
      list.style.display = open ? "block" : "none";
      btn.textContent = open ? "숨기기" : "더보기";
    });
  }

  // ===================================================
  // 5. 논문 저장 (내 서재)
  // ===================================================
  function initSavePapers() {
    const saveButton = document.querySelector(".save-selected-papers");
    if (!saveButton) return;

    let savedPaperIds = new Set();

    fetch("/affiliation/get_saved_papers/")
      .then((r) => r.json())
      .then((data) => {
        if (data && Array.isArray(data.saved_paper_ids)) {
          savedPaperIds = new Set(data.saved_paper_ids);
        }
      })
      .catch((e) => console.error("❌ 저장된 논문 조회 실패:", e));

    saveButton.addEventListener("click", function () {
      const selectedPapers = [];
      document
        .querySelectorAll("input[name='selected_papers']:checked")
        .forEach((checkbox) => {
          const paperId = checkbox.getAttribute("data-paper-id") || checkbox.value;
          if (paperId && !savedPaperIds.has(Number(paperId))) {
            selectedPapers.push(paperId);
          }
        });

      if (!selectedPapers.length) {
        alert("⚠️ 이미 저장된 논문을 제외한 새 논문이 없습니다.");
        return;
      }

      fetch("/affiliation/save_paper/", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": getCsrfToken(),
        },
        body: JSON.stringify({ paper_ids: selectedPapers }),
      })
        .then((r) => r.json())
        .then((data) => {
          if (data.message) {
            alert("✅ 선택한 논문이 저장되었습니다!");
          } else {
            alert("⚠ 논문 저장 실패: " + (data.error || ""));
          }
        })
        .catch((e) => console.error("⚠ 요청 실패:", e));
    });
  }

  // ===================================================
  // 6. 기관 좋아요
  // ===================================================
  function initLikeAffiliation() {
    document.body.addEventListener("click", function (event) {
      const target = event.target.closest(".like-affiliation");
      if (!target) return;

      const id = target.getAttribute("data-affiliation-id");
      if (!id) return;

      fetch(`/affiliation/like_affiliation/${id}/`, {
        method: "POST",
        headers: {
          "X-CSRFToken": getCsrfToken(),
          "Content-Type": "application/json",
        },
        credentials: "include",
      })
        .then((res) => {
          if (!res.ok) {
            if (res.status === 401) {
              alert("❌ 로그인 후 이용 가능합니다!");
              window.location.href = "/login";
            }
            throw new Error(`HTTP ${res.status}`);
          }
          return res.json();
        })
        .then((data) => {
          const spanId = `like-count-${id}`;
          if (data.liked) {
            target.innerHTML = `❤️ 좋아요 (<span id="${spanId}">${data.count}</span>)`;
            target.classList.add("btn-danger");
            target.classList.remove("btn-outline-danger");
          } else {
            target.innerHTML = `🤍 좋아요 (<span id="${spanId}">${data.count}</span>)`;
            target.classList.add("btn-outline-danger");
            target.classList.remove("btn-danger");
          }
        })
        .catch((e) => console.error("⚠ AJAX 요청 오류:", e));
    });
  }

  // ===================================================
  // 7. 정성적 분석 (Ollama)
  // ===================================================
  function initQualAnalysis() {
    const analysisButton = document.getElementById("analysisToggle");
    const loginRedirectButton = document.getElementById("loginRedirect");
    const analysisContent = document.getElementById("analysisContent");
    const analysisResult = document.getElementById("analysisResult");
    const loadingMessage = document.getElementById("loadingMessage");

    if (loginRedirectButton) {
      loginRedirectButton.addEventListener("click", () => {
        window.location.href = "/login/?next=" + window.location.pathname;
      });
    }

    if (!analysisButton) return;

    analysisButton.addEventListener("click", () => {
      const open = analysisContent.style.display !== "block";
      analysisContent.style.display = open ? "block" : "none";
      analysisButton.textContent = open ? "정성적 분석 숨기기" : "정성적 분석 보기";
      if (open && !analysisResult.innerHTML.trim()) {
        fetchOllama();
      }
    });

    function injectOnce(css, id = "ana-style") {
      const old = document.getElementById(id);
      if (old) old.remove();
      const style = document.createElement("style");
      style.id = id;
      style.textContent = css;
      document.head.appendChild(style);
    }

    function fetchOllama() {
      if (!affiliationId) return;

      loadingMessage.style.display = "block";

      fetch(`/affiliation/api/analyze_affiliation/${affiliationId}/`, {
        method: "POST",
        headers: {
          "X-CSRFToken": getCsrfToken(),
          "Content-Type": "application/json",
        },
        cache: "no-store",
      })
        .then((r) => r.json())
        .then((data) => {
          loadingMessage.style.display = "none";
          if (!data || !data.analysis) {
            analysisResult.textContent = "❌ 분석 결과를 가져올 수 없습니다.";
            return;
          }

          const m = data.analysis.match(/<style[^>]*>([\s\S]*?)<\/style>/i);
          if (m) {
            injectOnce(m[1]);
            analysisResult.innerHTML = data.analysis.replace(m[0], "");
          } else {
            analysisResult.innerHTML = data.analysis;
          }
        })
        .catch((err) => {
          console.error(err);
          loadingMessage.style.display = "none";
          analysisResult.textContent = "⚠️ 분석 요청에 실패했습니다.";
        });
    }
  }

  // ===================================================
  // 8. 페이지네이션
  // ===================================================
  function initPagination() {
    const paginationControls = document.getElementById("paginationControls");
    if (!paginationControls) return;

    function renderPagination(cur, total) {
      const maxButtons = 7;
      const half = Math.floor(maxButtons / 2);
      let start = Math.max(1, cur - half);
      let end = Math.min(total, start + maxButtons - 1);
      if (end - start + 1 < maxButtons) start = Math.max(1, end - maxButtons + 1);

      let html = `<div class="pagination">`;
      html += `<button class="page-btn" ${cur > 1 ? "" : "disabled"} data-page="1">« 처음</button>`;
      html += `<button class="page-btn" ${cur > 1 ? "" : "disabled"} data-page="${cur - 1}">‹ 이전</button>`;
      for (let p = start; p <= end; p++) {
        html += `<button class="page-btn ${p === cur ? "active" : ""}" data-page="${p}">${p}</button>`;
      }
      html += `<button class="page-btn" ${cur < total ? "" : "disabled"} data-page="${cur + 1}">다음 ›</button>`;
      html += `<button class="page-btn" ${cur < total ? "" : "disabled"} data-page="${total}">마지막 »</button>`;
      html += `</div>`;

      paginationControls.innerHTML = html;

      paginationControls.querySelectorAll(".page-btn").forEach((btn) => {
        btn.addEventListener("click", () => {
          const goto = Number(btn.getAttribute("data-page"));
          if (!goto || goto === cur || goto < 1 || goto > total) return;
          const next = new URL(window.location);
          next.searchParams.set("page", goto);
          next.searchParams.set("items_per_page", String(itemsPerPage || 10));
          window.location.href = next.toString();
        });
      });
    }

    renderPagination(currentPage, totalPages);
  }

  // ===================================================
  // DOMContentLoaded 진입점
  // ===================================================
  document.addEventListener("DOMContentLoaded", function () {
    initPdfDownload();
    initAffiliationAnalytics();
    renderAffiliationNetwork();
    initToggleAuthors();
    initSavePapers();
    initLikeAffiliation();
    initQualAnalysis();
    initPagination();
  });
})();
