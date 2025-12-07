// static/js/country.js
// 국가 상세 페이지 전용 스크립트 모음

(function () {
  // ===========================
  // 0. 공통 유틸
  // ===========================
  function getCountryConfig() {
    const el = document.getElementById("country-config");
    if (!el) return null;

    const ds = el.dataset || {};
    return {
      id: ds.id || "",
      name: ds.name || "",
      contentType: ds.contentType || "country",
      objectId: ds.objectId || ds.id || "",
      pageTitle: ds.pageTitle || ds.name || "",
      csrfToken: ds.csrfToken || "",
      currentPage: Number(ds.currentPage || "1"),
      totalPages: Number(ds.totalPages || "1"),
      itemsPerPage: Number(ds.itemsPerPage || "10"),
      isAuthenticated: ds.isAuthenticated === "true",
    };
  }

  function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== "") {
      const cookies = document.cookie.split(";");
      for (let i = 0; i < cookies.length; i++) {
        const cookie = cookies[i].trim();
        if (cookie.startsWith(name + "=")) {
          cookieValue = decodeURIComponent(
            cookie.substring(name.length + 1)
          );
          break;
        }
      }
    }
    return cookieValue;
  }

  // ===========================
  // 1. PDF 저장 + 다운로드
  // ===========================
  function setupPdfDownload(cfg) {
    const btn = document.getElementById("pdfDownload");
    if (!btn) return;
    if (typeof html2canvas === "undefined" || typeof jspdf === "undefined") {
      console.warn("html2canvas 또는 jsPDF 가 로드되지 않았습니다.");
      return;
    }

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
          const pdf = new jspdf.jsPDF("p", "mm", "a4");

          const imgWidth = 210; // A4 width
          const imgHeight = (canvas.height * imgWidth) / canvas.width;
          pdf.addImage(imgData, "PNG", 0, 0, imgWidth, imgHeight);

          // 파일명 안전하게 만들기
          let title = (cfg.pageTitle || "page")
            .trim()
            .toLowerCase()
            .replace(/[/\\?%*:|"<>]/g, "");
          if (!title) title = cfg.id || "page";

          const fileName = `${cfg.contentType || "country"}_${title}.pdf`;

          const pdfBlob = pdf.output("blob");
          const formData = new FormData();
          formData.append("pdf", pdfBlob, fileName);
          formData.append("content_type", cfg.contentType || "country");
          formData.append("object_id", cfg.objectId || cfg.id || "");
          formData.append("object_title", title);

          // 백엔드에서 author/pdf_upload 재사용 중이면 URL 그대로 쓰면 됨.
          const uploadUrl = "/author/pdf_upload/";

          return fetch(uploadUrl, {
            method: "POST",
            headers: {
              "X-CSRFToken": cfg.csrfToken || getCookie("csrftoken") || "",
            },
            body: formData,
          })
            .then((res) => res.json())
            .then((data) => {
              if (data && data.success) {
                pdf.save(fileName);
              } else {
                alert("⚠ PDF 저장 실패: " + (data && data.error ? data.error : ""));
                if (data && data.redirect_url) {
                  window.location.href = data.redirect_url;
                }
              }
            });
        })
        .catch((err) => {
          alert("❌ PDF 저장 실패: " + err.message);
          console.error(err);
        });
    });
  }

  // ===========================
  // 2. Chart.js + d3-wordcloud
  // ===========================
  // Chart 글로벌 테마
  if (typeof Chart !== "undefined") {
    Chart.defaults.font.family =
      "Pretendard, Inter, system-ui, -apple-system, Segoe UI, Roboto, Apple SD Gothic Neo, Noto Sans KR, sans-serif";
    Chart.defaults.color = "#4B4B4B";
    Chart.defaults.plugins.legend.display = false;
    Chart.defaults.plugins.tooltip.cornerRadius = 8;
    Chart.defaults.plugins.tooltip.padding = 10;
    Chart.defaults.animation.duration = 900;
    Chart.defaults.datasets.bar.borderRadius = 0; // 직각 막대
  }

  function hexToRgba(hex, alpha) {
    const c = hex.replace("#", "");
    const n = parseInt(c, 16);
    const r = (n >> 16) & 255,
      g = (n >> 8) & 255,
      b = n & 255;
    return `rgba(${r}, ${g}, ${b}, ${alpha})`;
  }

  function barOpts() {
    return {
      responsive: true,
      maintainAspectRatio: false,
      layout: { padding: { top: 6, right: 8, bottom: 0, left: 0 } },
      scales: {
        x: {
          grid: { display: false },
          ticks: { maxRotation: 30, autoSkip: false, font: { size: 11 } },
        },
        y: {
          beginAtZero: true,
          grid: {
            color: "rgba(105,0,184,.08)",
            drawBorder: false,
          },
        },
      },
      plugins: { legend: { display: false } },
    };
  }

  function renderBarChart(canvasId, labels, values, color) {
    if (typeof Chart === "undefined") return null;
    const el = document.getElementById(canvasId);
    if (!el) return null;

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

  async function initCountryAnalytics(cfg) {
    if (!cfg.id || typeof d3 === "undefined") return;

    const API_URL = `/country/api/country-analysis/${cfg.id}/`;

    let data;
    try {
      const res = await fetch(API_URL);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      data = await res.json();
    } catch (e) {
      console.error("분석 API 로딩 실패:", e);
      return;
    }

    // 1) 연도별 출판 논문
    const yLabels = Object.keys(data.year_chart_data || {});
    const yValues = Object.values(data.year_chart_data || {});
    renderBarChart("yearChart", yLabels, yValues, "#2E86AB");

    // 2) 파트별 논문
    const pLabels = Object.keys(data.part_chart_data || {});
    const pValues = Object.values(data.part_chart_data || {});
    renderBarChart("partChart", pLabels, pValues, "#F6A01A");

    // 3) 국가 키워드 워드클라우드 (d3-cloud, SVG)
    const wordsRaw = data.keyword_data || {};
    const MAX_WORDS = 30;
    const words = Object.entries(wordsRaw)
      .sort((a, b) => b[1] - a[1])
      .slice(0, MAX_WORDS)
      .map(([text, size]) => ({ text, size }));

    const svg = d3.select("#country-wordcloud");
    if (svg.empty()) return;

    const box = svg.node().getBoundingClientRect();
    const W = Math.max(300, box.width || 600);
    const H = Math.max(320, box.height || 350);

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
              .then((j) => {
                if (j.keyword_id) {
                  window.location.href = `/keyword/${j.keyword_id}/`;
                } else {
                  alert("해당 키워드 페이지를 찾을 수 없습니다.");
                }
              });
          });
      })
      .start();
  }

  // ===========================
  // 3. 공동 국가 네트워크 (renderNetworkChart)
  // ===========================
  function edgePointOnRect(cx, cy, child, halfW, halfH) {
    const dx = child.x - cx,
      dy = child.y - cy;
    if (dx === 0 && dy === 0) return { x: cx, y: cy };
    const t = 1 / Math.max(Math.abs(dx) / halfW, Math.abs(dy) / halfH);
    return { x: cx + dx * t, y: cy + dy * t };
  }

  function fitTextInCircle(text, r) {
    const maxPx = r * 1.65;
    const maxChar = Math.max(3, Math.floor(maxPx / 6.5));
    return text.length > maxChar ? text.slice(0, maxChar - 1) + "…" : text;
  }

  // 공통 네트워크 렌더러 (affiliation/author 버전과 동일 스타일)
  function renderNetworkChart({
    container,
    fetchUrl,
    mainName,
    mainId,
    maxChildren = 20,
    tooltipLabels = { pubs: "출판 수", count: "횟수" },
    mapChild,
  }) {
    if (typeof d3 === "undefined") return;

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

    fetch(fetchUrl)
      .then((r) => r.json())
      .then((data) => {
        const raw = (data.network_data || []).slice(0, maxChildren);
        const children = raw.map((d) =>
          mapChild
            ? mapChild(d)
            : {
                id: d.id,
                name: d.name,
                count: d.count,
                pubs: d.pubs ?? d.publication_count ?? d.paper_count ?? 0,
              }
        );

        const svg = d3.select(container).attr("preserveAspectRatio", "xMidYMid meet");
        if (svg.empty()) return;
        svg.selectAll("*").remove();

        const box = svg.node().getBoundingClientRect();
        const W = Math.max(560, box.width || 600);
        const H = Math.max(420, box.height || 420);
        svg.attr("viewBox", `0 0 ${W} ${H}`);

        const cx = W / 2,
          cy = H / 2;
        const edgeMargin = 24;
        const maxR = Math.min(W, H) / 2 - (edgeMargin + 32);

        const nodes = [];
        const mainFontSize = 14;
        const mainFontWeight = 600;

        // 메인 노드 텍스트 너비 측정
        const ghost = svg
          .append("text")
          .attr("x", -9999)
          .attr("y", -9999)
          .attr("font-size", mainFontSize)
          .attr("font-weight", mainFontWeight)
          .text(mainName);
        const textWidth = ghost.node().getBBox().width;
        ghost.remove();

        const paddingX = 28;
        const paddingY = 16;
        let mainW = Math.max(130, Math.min(W * 0.85, textWidth + paddingX * 2));
        let mainH = Math.max(50, Math.min(H * 0.3, mainFontSize + paddingY * 2));

        const mainNode = {
          id: mainId,
          name: mainName,
          type: "main",
          x: cx,
          y: cy,
          mainW,
          mainH,
        };
        nodes.push(mainNode);

        // 스케일들
        const counts = children.map((d) => +d.count || 0);
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

        const pubVals = children.map((d) => +d.pubs || 0);
        const minP = pubVals.length ? d3.min(pubVals) : 0;
        const maxP = pubVals.length ? d3.max(pubVals) : 1;

        const childR = d3
          .scaleSqrt()
          .domain([Math.max(0, minP), Math.max(1, maxP)])
          .range([25, 35]);

        // 배치 계산
        const MIN_EDGE_PX = 50;
        const MAX_EDGE_PX = 90;
        const n = children.length;
        const baseStep = (2 * Math.PI) / Math.max(1, n);
        const mainHalf = Math.max(mainW, mainH) / 2;
        const canvasHardMax = Math.min(W, H) / 2 - 24;

        const minRing = mainHalf + MIN_EDGE_PX;
        const userMaxR = Math.min(mainHalf + MAX_EDGE_PX, canvasHardMax);
        const span = Math.max(40, userMaxR - minRing);

        const longBase = userMaxR;
        const shortBase = minRing + span * 0.05;

        const angleJitterScale = baseStep * 0.2;
        const randN = d3.randomNormal(0, span * 0.05);
        const fineJ = () => (Math.random() - 0.5) * 8;

        const inwardScale = d3
          .scaleLinear()
          .domain([minC, maxC || 1])
          .range([0, Math.min(30, span * 0.1)]);

        children.forEach((d, i) => {
          const a = i * baseStep - Math.PI / 2 + (Math.random() - 0.5) * angleJitterScale;
          const inward = inwardScale(d.count || 0);

          let baseRad = i % 2 === 0 ? longBase : shortBase;
          if (i % 4 === 0) baseRad = userMaxR;

          const r = Math.max(
            minRing,
            Math.min(userMaxR, baseRad + randN() + fineJ() - inward)
          );

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

        const links = children.map((d) => ({
          source: mainId,
          target: d.id,
          count: d.count,
        }));

        // 링크
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

        // 노드
        const gNodes = svg
          .append("g")
          .attr("class", "nc-nodes")
          .selectAll("g")
          .data(nodes)
          .enter()
          .append("g")
          .attr("transform", (d) => `translate(${d.x},${d.y})`);

        // 메인 노드 (둥근 사각형)
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
          .text((d) => d.name);

        // 자식 노드 (원형)
        const gChild = gNodes.filter((d) => d.type === "child");
        gChild
          .append("circle")
          .attr("r", (d) => d.r)
          .attr("fill", PALETTE.childFill)
          .attr("stroke", PALETTE.childStroke)
          .attr("stroke-width", 2)
          .style("cursor", "pointer")
          .on("click", (e, d) => d.id && (window.location.href = `/country/${d.id}/`))
          .on("mouseenter", function (e, d) {
            d3.select(this).attr("stroke-width", 3).attr("stroke", PALETTE.hover);
            linkSel
              .filter((l) => l.target === d.id)
              .attr("stroke", PALETTE.linkHigh)
              .attr("stroke-width", linkWidth(d.count) + 2);
            tip.html(tooltipHtml(d)).style("display", "block");
          })
          .on("mousemove", (e) => {
            tip.style("left", e.pageX + 12 + "px").style("top", e.pageY - 18 + "px");
          })
          .on("mouseleave", function (e, d) {
            d3.select(this)
              .attr("stroke-width", 2)
              .attr("stroke", PALETTE.childStroke);
            linkSel
              .filter((l) => l.target === d.id)
              .attr("stroke", linkColor(d.count))
              .attr("stroke-width", linkWidth(d.count));
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

        // 툴팁
        d3.selectAll(".nc-tooltip").remove();
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

        function tooltipHtml(d) {
          return `<div style="font-weight:800;margin-bottom:4px;">${d.name}</div>
                  <div>${tooltipLabels.pubs}: <b>${d.pubs}</b></div>
                  <div>${tooltipLabels.count}: <b>${d.count}</b></div>`;
        }
      })
      .catch((e) => console.error("국가 네트워크 로딩 실패:", e));
  }

  function initCountryNetwork(cfg) {
    if (!cfg.id) return;
    renderNetworkChart({
      container: "#networkChart",
      fetchUrl: `/country/api/country-analysis/${cfg.id}/`,
      mainName: cfg.name,
      mainId: cfg.id,
      maxChildren: 20,
      tooltipLabels: { pubs: "출판 수", count: "공동 연구 횟수" },
      mapChild: (d) => ({
        id: d.id,
        name: d.name,
        count: d.count,
        pubs: d.pubs ?? d.publication_count ?? d.paper_count ?? 0,
      }),
    });
  }

  // ===========================
  // 4. 정성적 분석 (Ollama)
  // ===========================
  function setupAnalysisPanel(cfg) {
    const analysisButton = document.getElementById("analysisToggle");
    const loginRedirectButton = document.getElementById("loginRedirect");
    const analysisContent = document.getElementById("analysisContent");
    const analysisResult = document.getElementById("analysisResult");
    const loadingMessage = document.getElementById("loadingMessage");

    if (!analysisContent || !analysisResult) return;

    if (loginRedirectButton) {
      loginRedirectButton.addEventListener("click", () => {
        window.location.href = "/login/?next=" + window.location.pathname;
      });
    }

    if (analysisButton) {
      analysisButton.addEventListener("click", () => {
        const open = analysisContent.style.display !== "block";
        analysisContent.style.display = open ? "block" : "none";
        analysisButton.textContent = open ? "분석 숨기기" : "정성적 분석 보기";
        if (open && !analysisResult.innerHTML.trim()) {
          fetchOllamaCountryAnalysis();
        }
      });
    }

    function fetchOllamaCountryAnalysis() {
      if (!cfg.id) {
        console.error("❌ 국가 ID가 올바르지 않습니다.");
        return;
      }

      loadingMessage.style.display = "block";

      fetch(`/country/api/analyze_country/${cfg.id}/`, {
        method: "POST",
        headers: {
          "X-CSRFToken": cfg.csrfToken || getCookie("csrftoken") || "",
          "Content-Type": "application/json",
        },
        cache: "no-store",
      })
        .then((res) => res.json())
        .then((data) => {
          loadingMessage.style.display = "none";
          if (data && data.analysis) {
            analysisResult.innerHTML = data.analysis;
          } else {
            analysisResult.innerHTML =
              "<p style='color:red;'>❌ 분석 결과를 가져올 수 없습니다.</p>";
          }
        })
        .catch((err) => {
          loadingMessage.style.display = "none";
          console.error("정성적 분석 오류:", err);
          analysisResult.innerHTML =
            "<p style='color:red;'>⚠ 분석 요청에 실패했습니다.</p>";
        });
    }
  }

  // ===========================
  // 5. 논문 저장(내 서재) – 국가 버전
  // ===========================
  function setupSaveSelectedPapers(cfg) {
    const btn = document.querySelector(".save-selected-papers");
    if (!btn) return;

    let savedPaperIds = new Set();

    // 이미 저장된 논문 ID 먼저 불러오기
    fetch(`/country/api/${cfg.id}/`)
      .then((r) => r.json())
      .then((data) => {
        if (Array.isArray(data.saved_paper_ids)) {
          savedPaperIds = new Set(
            data.saved_paper_ids.map((x) => Number(x))
          );
        }
      })
      .catch((e) => console.warn("저장된 논문 목록 조회 실패:", e));

    btn.addEventListener("click", () => {
      const selected = [];
      document
        .querySelectorAll("input[name='selected_papers']:checked")
        .forEach((cb) => {
          const pid = Number(cb.getAttribute("data-paper-id") || cb.value);
          if (pid && !savedPaperIds.has(pid)) {
            selected.push(pid);
          }
        });

      if (!selected.length) {
        alert("⚠️ 이미 저장된 논문을 제외한 새 논문이 없습니다.");
        return;
      }

      fetch("/country/save_paper/", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": cfg.csrfToken || getCookie("csrftoken") || "",
        },
        body: JSON.stringify({ paper_ids: selected }),
      })
        .then((r) => r.json())
        .then((data) => {
          if (data && data.message) {
            alert("✅ 선택한 논문이 저장되었습니다!");
            selected.forEach((id) => savedPaperIds.add(id));
          } else {
            alert("⚠ 논문 저장 실패: " + (data && data.error ? data.error : ""));
          }
        })
        .catch((e) => console.error("논문 저장 요청 실패:", e));
    });
  }

  // ===========================
  // 6. 좋아요(국가) – 버튼 클래스 .like-country
  // ===========================
  function setupLikeCountry(cfg) {
    document.body.addEventListener("click", (event) => {
      const btn = event.target.closest(".like-country");
      if (!btn) return;

      const countryId = btn.getAttribute("data-country-id") || cfg.id;
      const countSpanId = `like-count-${countryId}`;
      const likeCountElement = document.getElementById(countSpanId);

      fetch(`/country/like_country/${countryId}/`, {
        method: "POST",
        headers: {
          "X-CSRFToken": cfg.csrfToken || getCookie("csrftoken") || "",
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
            throw new Error(`HTTP 오류: ${res.status}`);
          }
          return res.json();
        })
        .then((data) => {
          if (!data) return;
          // 버튼 상태 업데이트
          if (data.liked) {
            btn.innerHTML = `❤️ 좋아요 (<span id="${countSpanId}">${data.count}</span>)`;
            btn.classList.add("btn-danger");
            btn.classList.remove("btn-outline-danger");
          } else {
            btn.innerHTML = `🤍 좋아요 (<span id="${countSpanId}">${data.count}</span>)`;
            btn.classList.add("btn-outline-danger");
            btn.classList.remove("btn-danger");
          }
          if (likeCountElement) {
            likeCountElement.textContent = data.count;
          }
        })
        .catch((e) => console.error("좋아요 요청 오류:", e));
    });
  }

  // ===========================
  // 7. 페이지네이션
  // ===========================
  function setupPagination(cfg) {
    const paginationControls = document.getElementById("paginationControls");
    if (!paginationControls) return;

    function renderPagination(currentPage, totalPages) {
      const maxButtons = 7;
      const half = Math.floor(maxButtons / 2);
      let start = Math.max(1, currentPage - half);
      let end = Math.min(totalPages, start + maxButtons - 1);
      if (end - start + 1 < maxButtons) {
        start = Math.max(1, end - maxButtons + 1);
      }

      let html = `<div class="pagination">`;
      html += `<button class="page-btn" ${
        currentPage > 1 ? "" : "disabled"
      } data-page="1">« 처음</button>`;
      html += `<button class="page-btn" ${
        currentPage > 1 ? "" : "disabled"
      } data-page="${currentPage - 1}">‹ 이전</button>`;

      for (let p = start; p <= end; p++) {
        html += `<button class="page-btn ${
          p === currentPage ? "active" : ""
        }" data-page="${p}">${p}</button>`;
      }

      html += `<button class="page-btn" ${
        currentPage < totalPages ? "" : "disabled"
      } data-page="${currentPage + 1}">다음 ›</button>`;
      html += `<button class="page-btn" ${
        currentPage < totalPages ? "" : "disabled"
      } data-page="${totalPages}">마지막 »</button>`;
      html += `</div>`;

      paginationControls.innerHTML = html;

      paginationControls.querySelectorAll(".page-btn").forEach((btn) => {
        btn.addEventListener("click", () => {
          const goto = parseInt(btn.getAttribute("data-page"), 10);
          if (
            !isNaN(goto) &&
            goto >= 1 &&
            goto <= totalPages &&
            goto !== currentPage
          ) {
            const next = new URL(window.location);
            next.searchParams.set("page", goto);
            next.searchParams.set("items_per_page", String(cfg.itemsPerPage));
            window.location.href = next.toString();
          }
        });
      });
    }

    renderPagination(cfg.currentPage, cfg.totalPages);
  }

  // ===========================
  // 8. 초기화
  // ===========================
  document.addEventListener("DOMContentLoaded", function () {
    const cfg = getCountryConfig();
    if (!cfg) {
      console.warn("country-config 요소를 찾을 수 없습니다.");
      return;
    }

    setupPdfDownload(cfg);
    initCountryAnalytics(cfg);
    initCountryNetwork(cfg);
    setupAnalysisPanel(cfg);
    setupSaveSelectedPapers(cfg);
    setupLikeCountry(cfg);
    setupPagination(cfg);
  });
})();
