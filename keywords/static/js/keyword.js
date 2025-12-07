// static/js/keyword.js

(function () {
  const cfg = window.keywordConfig || {};

  // ---------------- 공통 유틸 ----------------
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

  // ---------------- PDF 다운로드 ----------------
  async function handlePdfDownload() {
    const ok = window.confirm("📄 PDF를 다운로드 하시겠습니까?");
    if (!ok) return;

    const targetElement = document.body;

    try {
      const canvas = await html2canvas(targetElement, {
        scale: 2,
        useCORS: true,
        allowTaint: true,
        logging: false,
      });

      const imgData = canvas.toDataURL("image/png");
      const pdf = new jspdf.jsPDF("p", "mm", "a4");

      const imgWidth = 210;
      const imgHeight = (canvas.height * imgWidth) / canvas.width;

      pdf.addImage(imgData, "PNG", 0, 0, imgWidth, imgHeight);

      // 파일명 구성
      let contentType = cfg.contentType || "keyword";
      let objectId = cfg.objectId || cfg.id || "0";
      let titleRaw = (cfg.pageTitle || cfg.name || "페이지").trim().toLowerCase();
      let objectTitle = titleRaw.replace(/[/\\?%*:|"<>]/g, "");
      let fileName =
        contentType === "author" && objectTitle === "eom"
          ? "author_eom.pdf"
          : `${contentType}_${objectTitle || "page"}.pdf`;

      // 서버에 저장
      const pdfBlob = pdf.output("blob");
      const formData = new FormData();
      formData.append("pdf", pdfBlob, fileName);
      formData.append("content_type", contentType);
      formData.append("object_id", objectId);
      formData.append("object_title", objectTitle);

      const resp = await fetch("/keyword/pdf_upload/", {
        method: "POST",
        headers: {
          "X-CSRFToken": cfg.csrfToken || getCookie("csrftoken"),
        },
        body: formData,
      });

      const data = await resp.json();

      if (resp.ok && data && data.success) {
        pdf.save(fileName);
      } else if (resp.status === 403) {
        alert("⚠ 로그인 후 이용 가능합니다.");
        window.location.href = "/login/";
      } else {
        alert("⚠ PDF 저장 실패: " + (data && data.error ? data.error : "알 수 없는 오류"));
      }
    } catch (e) {
      console.error(e);
      alert("❌ PDF 저장 실패: " + e.message);
    }
  }

  // ---------------- 연도별 차트 ----------------
  function initYearlyChart() {
    const jsonEl = document.getElementById("yearly-data");
    if (!jsonEl) {
      console.warn("yearly-data 스크립트 태그를 찾을 수 없습니다.");
      return;
    }

    let yearCounts = {};
    try {
      yearCounts = JSON.parse(jsonEl.textContent || "{}");
    } catch (e) {
      console.error("year_counts_json 파싱 오류:", e);
      return;
    }

    const labels = ["2019", "2020", "2021", "2022", "2023", "2024"];
    const dataValues = labels.map((year) => {
      const v = yearCounts[year];
      return v === undefined ? 0 : Number(v);
    });

    if (dataValues.every((v) => v === 0)) {
      console.warn("연도별 데이터가 없어 차트를 그리지 않습니다.");
      return;
    }

    const maxVal = Math.max(...dataValues, 1);
    const stepSize = Math.max(1, Math.ceil(maxVal / 5));

    const canvas = document.getElementById("yearlyKeywordChart");
    if (!canvas) {
      console.error("yearlyKeywordChart 캔버스를 찾을 수 없습니다.");
      return;
    }

    const ctx = canvas.getContext("2d");

    // Chart.js 전역 옵션(필요시)
    if (typeof Chart !== "undefined") {
      Chart.defaults.font.family =
        "Pretendard, Inter, system-ui, -apple-system, Segoe UI, Roboto, Apple SD Gothic Neo, Noto Sans KR, sans-serif";
    }

    new Chart(ctx, {
      type: "bar",
      data: {
        labels,
        datasets: [
          {
            label: "출현 빈도",
            data: dataValues,
            backgroundColor: "rgba(75, 192, 192, 0.5)",
            borderColor: "rgba(75, 192, 192, 1)",
            borderWidth: 1,
          },
        ],
      },
      options: {
        responsive: false,
        maintainAspectRatio: false,
        scales: {
          y: {
            beginAtZero: true,
            max: maxVal + 1,
            ticks: {
              stepSize: stepSize,
            },
          },
        },
      },
    });
  }

  // ---------------- 연관 키워드 네트워크 (D3) ----------------
  function initKeywordNetwork() {
    if (typeof d3 === "undefined") return;

    const scriptEl = document.getElementById("related-keywords-data");
    const svgContainer = document.querySelector("#kwNetworkChart");
    if (!scriptEl || !svgContainer) return;

    let arr = [];
    try {
      arr = JSON.parse((scriptEl.textContent || "").trim() || "[]");
    } catch (e) {
      console.error("related_keywords_json 파싱 실패:", e);
      return;
    }

    const children = arr.map((d, idx) => ({
      id: d.id ?? idx + 1,
      name: d.name ?? d.keyword ?? "N/A",
      count: d.frequency ?? d.count ?? 1,
      freq: d.frequency ?? d.count ?? 1,
    }));

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

    const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
    const fitTextInCircle = (t, r) => {
      const m = r * 1.65;
      const c = Math.max(3, Math.floor(m / 6.5));
      return t.length > c ? t.slice(0, c - 1) + "…" : t;
    };
    const measureText = (svg, text, fs = 14, fw = 600, ff = "inherit") => {
      const ghost = svg
        .append("text")
        .attr("x", -9999)
        .attr("y", -9999)
        .attr("font-size", fs)
        .attr("font-weight", fw)
        .attr("font-family", ff)
        .text(text);
      const w = ghost.node().getBBox().width;
      ghost.remove();
      return w;
    };
    const edgePointOnRect = (cx, cy, ch, hw, hh) => {
      const dx = ch.x - cx;
      const dy = ch.y - cy;
      if (!dx && !dy) return { x: cx, y: cy };
      const t = 1 / Math.max(Math.abs(dx) / hw, Math.abs(dy) / hh);
      return { x: cx + dx * t, y: cy + dy * t };
    };

    const svg = d3.select(svgContainer).attr("preserveAspectRatio", "xMidYMid meet");
    svg.selectAll("*").remove();
    d3.selectAll(".kw-tooltip").remove();

    const box = svg.node().getBoundingClientRect();
    const W = Math.max(560, box.width || 600);
    const H = Math.max(420, box.height || 420);
    svg.attr("viewBox", `0 0 ${W} ${H}`);

    const cx = W / 2;
    const cy = H / 2;

    /* 그라데이션 */
    const defs = svg.append("defs");
    const grad = defs
      .append("linearGradient")
      .attr("id", "kwGradMain")
      .attr("x1", "0%")
      .attr("x2", "100%")
      .attr("y1", "0%")
      .attr("y2", "100%");
    grad.append("stop").attr("offset", "0%").attr("stop-color", PALETTE.main1);
    grad.append("stop").attr("offset", "100%").attr("stop-color", PALETTE.main2);

    const mainName = cfg.name || "Keyword";
    const mainId = cfg.id || "main";

    const mainFS = 14;
    const mainFW = 700;
    const textW = measureText(svg, mainName, mainFS, mainFW);
    const mainW = clamp(textW + 28 * 2, 130, W * 0.85);
    const mainH = clamp(mainFS + 16 * 2, 50, H * 0.3);

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

    const freqs = children.map((d) => +d.freq || +d.count || 0);
    const minF = freqs.length ? d3.min(freqs) : 0;
    const maxF = freqs.length ? d3.max(freqs) : 1;

    const childR = d3
      .scaleSqrt()
      .domain([Math.max(0, minF), Math.max(1, maxF)])
      .range([22, 34]);

    const nodes = [];
    const mainNode = { id: mainId, name: mainName, type: "main", x: cx, y: cy, mainW, mainH };
    nodes.push(mainNode);

    const n = children.length;
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
    const inwardScale = d3
      .scaleLinear()
      .domain([minC, maxC || 1])
      .range([0, Math.min(30, span * 0.1)]);

    children.forEach((d, i) => {
      const a = i * step - Math.PI / 2 + (Math.random() - 0.5) * jitterA;
      let base = i % 2 === 0 ? longBase : shortBase;
      if (i % 4 === 0) base = userMaxR;
      const inward = inwardScale(d.count || 0);
      const r = Math.max(
        minRing,
        Math.min(userMaxR, base + randN() + fine() - inward)
      );

      nodes.push({
        id: d.id,
        name: d.name,
        type: "child",
        x: cx + Math.cos(a) * r,
        y: cy + Math.sin(a) * r,
        r: childR(d.freq || d.count || 0),
        count: d.count || 0,
        freq: d.freq || d.count || 0,
      });
    });

    const links = children.map((d) => ({
      source: mainId,
      target: d.id,
      count: d.count || 0,
    }));

    const gLinks = svg.append("g").attr("class", "kw-links");
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
      .attr("class", "kw-nodes")
      .selectAll("g")
      .data(nodes)
      .enter()
      .append("g")
      .attr("transform", (d) => `translate(${d.x},${d.y})`);

    // 메인 노드
    const gMain = gNodes.filter((d) => d.type === "main");
    gMain
      .append("rect")
      .attr("x", (d) => -d.mainW / 2)
      .attr("y", (d) => -d.mainH / 2)
      .attr("width", (d) => d.mainW)
      .attr("height", (d) => d.mainH)
      .attr("rx", 18)
      .attr("fill", "url(#kwGradMain)")
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

    // 툴팁
    const tip = d3
      .select("body")
      .append("div")
      .attr("class", "kw-tooltip")
      .style("position", "absolute")
      .style("z-index", "9999")
      .style("background", "#111")
      .style("color", "#fff")
      .style("padding", "8px 10px")
      .style("border-radius", "8px")
      .style("box-shadow", "0 6px 16px rgba(0,0,0,.35)")
      .style("font-size", "12px")
      .style("display", "none");

    const tooltipHtml = (d) =>
      `<div style="font-weight:800;margin-bottom:4px;">${d.name}</div>
       <div>연관도(빈도): <b>${d.freq}</b></div>
       <div>공동 키워드 횟수: <b>${d.count}</b></div>`;

    // 자식 노드
    const gChild = gNodes.filter((d) => d.type === "child");
    gChild
      .append("circle")
      .attr("r", (d) => d.r)
      .attr("fill", PALETTE.childFill)
      .attr("stroke", PALETTE.childStroke)
      .attr("stroke-width", 2)
      .style("cursor", "pointer")
      .on("click", (e, d) => {
        if (d.id) window.location.href = `/keyword/${d.id}/`;
      })
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
  }

  // ---------------- 내 서재 담기 ----------------
  function initSaveToLibrary() {
    const saveButton = document.querySelector(".save-selected-papers");
    if (!saveButton) return;

    fetch("/keyword/get_saved_papers/")
      .then((r) => r.json())
      .then((data) => {
        if (data.error) {
          console.error("❌ 저장된 논문 조회 실패:", data.error);
          return;
        }

        const savedPaperIds = new Set(data.saved_paper_ids || []);

        saveButton.addEventListener("click", () => {
          const selectedPapers = [];
          document
            .querySelectorAll("input[name='selected_papers']:checked")
            .forEach((checkbox) => {
              const paperId = checkbox.getAttribute("data-paper-id") || checkbox.value;
              if (paperId && !savedPaperIds.has(Number(paperId))) {
                selectedPapers.push(paperId);
              }
            });

          if (selectedPapers.length === 0) {
            alert("⚠️ 이미 저장된 논문을 제외한 새 논문이 없습니다.");
            return;
          }

          fetch("/keyword/save_paper/", {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              "X-CSRFToken": cfg.csrfToken || getCookie("csrftoken"),
            },
            body: JSON.stringify({ paper_ids: selectedPapers }),
          })
            .then((r) => r.json())
            .then((data2) => {
              if (data2.message) {
                alert("✅ 선택한 논문이 저장되었습니다!");
              } else {
                alert("⚠ 논문 저장 실패: " + data2.error);
              }
            })
            .catch((e) => console.error("⚠ 요청 실패:", e));
        });
      })
      .catch((e) => console.error("❌ 저장된 논문 목록 조회 오류:", e));
  }

  // ---------------- 좋아요 버튼 ----------------
  function initLikeButton() {
    document.body.addEventListener("click", (event) => {
      const target = event.target.closest(".like-keyword");
      if (!target) return;

      const keywordId = target.getAttribute("data-keyword-id");
      if (!keywordId) return;

      fetch(`/keyword/like_keyword/${keywordId}/`, {
        method: "POST",
        headers: {
          "X-CSRFToken": cfg.csrfToken || getCookie("csrftoken"),
          "Content-Type": "application/json",
        },
        credentials: "include",
      })
        .then((response) => {
          if (!response.ok) {
            if (response.status === 401) {
              alert("❌ 로그인 후 이용 가능합니다!");
              window.location.href = "/login";
            }
            throw new Error(`HTTP 오류! 상태 코드: ${response.status}`);
          }
          return response.json();
        })
        .then((data) => {
          const likeCountElement = document.getElementById(`like-count-${keywordId}`);
          if (likeCountElement) {
            likeCountElement.textContent = data.count;
          }
          if (data.liked) {
            target.classList.add("btn-danger");
            target.classList.remove("btn-outline-danger");
          } else {
            target.classList.add("btn-outline-danger");
            target.classList.remove("btn-danger");
          }
          const totalLikes = document.getElementById("total-likes");
          if (totalLikes) totalLikes.textContent = data.count;
        })
        .catch((error) => console.error("⚠ AJAX 요청 오류:", error));
    });
  }

  // ---------------- 탭 상태 유지 ----------------
  function initTabPersistence() {
    const activeTab = localStorage.getItem("keyword_activeTab");
    if (activeTab) {
      const selectedTab = document.querySelector(`[data-bs-target="${activeTab}"]`);
      if (selectedTab) selectedTab.click();
    }

    document.querySelectorAll(".keyword-tabs .nav-link").forEach((tab) => {
      tab.addEventListener("click", function () {
        localStorage.setItem("keyword_activeTab", this.getAttribute("data-bs-target"));
      });
    });
  }

  // ---------------- 정성적 분석 ----------------
  function initQualitativeAnalysis() {
    const analysisButton = document.getElementById("analysisToggle");
    const loginRedirectButton = document.getElementById("loginRedirect");
    const analysisContent = document.getElementById("analysisContent");
    const analysisResult = document.getElementById("analysisResult");
    const loadingMessage = document.getElementById("loadingMessage");

    const keywordId = cfg.id || "0";

    if (loginRedirectButton) {
      loginRedirectButton.addEventListener("click", () => {
        window.location.href = "/login/?next=" + window.location.pathname;
      });
    }

    if (analysisButton) {
      analysisButton.addEventListener("click", () => {
        const open = analysisContent.style.display !== "block";
        analysisContent.style.display = open ? "block" : "none";
        analysisButton.textContent = open ? "정성적 분석 숨기기" : "정성적 분석 보기";

        if (open && !analysisResult.innerHTML.trim()) {
          if (!keywordId || keywordId === "0") return;
          loadingMessage.style.display = "block";

          fetch(`/keyword/api/analyze_keyword/${keywordId}/`, {
            method: "POST",
            headers: {
              "X-CSRFToken": cfg.csrfToken || getCookie("csrftoken"),
              "Content-Type": "application/json",
            },
          })
            .then((r) => r.json())
            .then((data) => {
              loadingMessage.style.display = "none";
              if (data && data.analysis) {
                analysisResult.innerHTML = data.analysis;
              } else {
                analysisResult.innerHTML =
                  "<p>❌ 분석 결과를 가져올 수 없습니다.</p>";
              }
            })
            .catch((e) => {
              console.error(e);
              loadingMessage.style.display = "none";
              analysisResult.innerHTML =
                "<p>⚠️ 분석 요청에 실패했습니다.</p>";
            });
        }
      });
    }
  }

  // ---------------- 페이지네이션 ----------------
  function initPagination() {
    const paginationControls = document.getElementById("paginationControls");
    if (!paginationControls) return;

    const currentPage = Number(cfg.currentPage || 1);
    const totalPages = Number(cfg.totalPages || 1);
    const itemsPerPage = Number(cfg.itemsPerPage || 10);

    function renderPagination(page, total) {
      const maxButtons = 7;
      const half = Math.floor(maxButtons / 2);
      let start = Math.max(1, page - half);
      let end = Math.min(total, start + maxButtons - 1);
      if (end - start + 1 < maxButtons) {
        start = Math.max(1, end - maxButtons + 1);
      }

      let html = `<div class="pagination">`;
      html += `<button class="page-btn" ${
        page > 1 ? "" : "disabled"
      } data-page="1">« 처음</button>`;
      html += `<button class="page-btn" ${
        page > 1 ? "" : "disabled"
      } data-page="${page - 1}">‹ 이전</button>`;
      for (let p = start; p <= end; p++) {
        html += `<button class="page-btn ${
          p === page ? "active" : ""
        }" data-page="${p}">${p}</button>`;
      }
      html += `<button class="page-btn" ${
        page < total ? "" : "disabled"
      } data-page="${page + 1}">다음 ›</button>`;
      html += `<button class="page-btn" ${
        page < total ? "" : "disabled"
      } data-page="${total}">마지막 »</button>`;
      html += `</div>`;

      paginationControls.innerHTML = html;

      paginationControls.querySelectorAll(".page-btn").forEach((btn) => {
        btn.addEventListener("click", () => {
          const goto = parseInt(btn.getAttribute("data-page"), 10);
          if (!isNaN(goto) && goto >= 1 && goto <= total && goto !== page) {
            const next = new URL(window.location);
            next.searchParams.set("page", goto);
            next.searchParams.set("items_per_page", String(itemsPerPage));
            window.location.href = next.toString();
          }
        });
      });
    }

    renderPagination(currentPage, totalPages);
  }

  // ---------------- DOMContentLoaded ----------------
  document.addEventListener("DOMContentLoaded", function () {
    const pdfBtn = document.getElementById("pdfDownload");
    if (pdfBtn) pdfBtn.addEventListener("click", handlePdfDownload);

    initYearlyChart();
    initKeywordNetwork();
    initSaveToLibrary();
    initLikeButton();
    initTabPersistence();
    initQualitativeAnalysis();
    initPagination();
  });
})();
