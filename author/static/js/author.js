// static/js/author.js

/**********************************************************
 * 0. 공통 유틸
 **********************************************************/
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

function getAuthorConfig() {
  return window.authorConfig || {};
}

/**********************************************************
 * 1. PDF 다운로드 + 서버 업로드(html2canvas + jsPDF)
 **********************************************************/
document.addEventListener("DOMContentLoaded", function () {
  const btn = document.getElementById("pdfDownload");
  if (!btn) return;

  btn.addEventListener("click", function () {
    const ok = confirm("📄 PDF를 다운로드 하시겠습니까?");
    if (!ok) return;

    const cfg = getAuthorConfig();
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
        const imgWidth = 210;
        const imgHeight = (canvas.height * imgWidth) / canvas.width;

        pdf.addImage(imgData, "PNG", 0, 0, imgWidth, imgHeight);

        let contentType = cfg.contentType || "author";
        let objectId = cfg.objectId || "0";
        let objectTitle =
          (cfg.pageTitle || "페이지")
            .trim()
            .toLowerCase()
            .replace(/[/\\?%*:|"<>]/g, "") || "page";

        const fileName =
          contentType === "author" && objectTitle === "eom"
            ? "author_eom.pdf"
            : `${contentType}_${objectTitle}.pdf`;

        const formData = new FormData();
        formData.append("pdf", pdf.output("blob"), fileName);
        formData.append("content_type", contentType);
        formData.append("object_id", objectId);
        formData.append("object_title", objectTitle);

        return fetch("/author/pdf_upload/", {
          method: "POST",
          body: formData,
          headers: {
            "X-CSRFToken": cfg.csrfToken || getCookie("csrftoken"),
          },
        }).then((response) =>
          response.json().then((data) => ({
            httpStatus: response.status,
            data,
          })),
        );
      })
      .then(({ httpStatus, data }) => {
        if (data && data.success) {
          // 서버 저장 성공 시에만 다운로드
          const cfg = getAuthorConfig();
          let contentType = cfg.contentType || "author";
          let objectTitle =
            (cfg.pageTitle || "페이지")
              .trim()
              .toLowerCase()
              .replace(/[/\\?%*:|"<>]/g, "") || "page";
          const fileName =
            contentType === "author" && objectTitle === "eom"
              ? "author_eom.pdf"
              : `${contentType}_${objectTitle}.pdf`;

          const pdf = new jspdf.jsPDF("p", "mm", "a4");
          // 위에서 이미 pdf를 만들었지만, 간단히 다시 한 번 만들어 저장만 수행
          // (이미지 다시 캡처 안 함)
          pdf.save(fileName);
        } else if (data && data.error) {
          alert("⚠ " + data.error);
          if (httpStatus === 403) {
            window.location.href = "/login/";
          }
        }
      })
      .catch((error) => {
        alert("❌ PDF 저장 실패: " + error.message);
        console.error(error);
      });
  });
});

/**********************************************************
 * 2. Chart.js 기본 설정 + 막대 차트 렌더링
 **********************************************************/
if (window.Chart) {
  Chart.defaults.font.family =
    "Pretendard, Inter, system-ui, -apple-system, Segoe UI, Roboto, Apple SD Gothic Neo, Noto Sans KR, sans-serif";
  Chart.defaults.color = "#4B4B4B";
  Chart.defaults.plugins.legend.display = false;
  Chart.defaults.plugins.tooltip.cornerRadius = 8;
  Chart.defaults.plugins.tooltip.padding = 10;
  Chart.defaults.animation.duration = 900;
  Chart.defaults.datasets.bar.borderRadius = 0;
  Chart.defaults.datasets.bar.maxBarThickness = 36;
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
        grid: { color: "rgba(105,0,184,.08)", drawBorder: false },
      },
    },
    plugins: { legend: { display: false } },
  };
}

function renderBarChart(canvasId, labels, values, colorHex) {
  if (!window.Chart) return;
  const el = document.getElementById(canvasId);
  if (!el) return;
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
          borderColor: colorHex,
          backgroundColor: hexToRgba(colorHex, 0.35),
          hoverBackgroundColor: hexToRgba(colorHex, 0.6),
          hoverBorderColor: colorHex,
          borderRadius: 0,
        },
      ],
    },
    options: barOpts(),
  });
}

/**********************************************************
 * 3. 저자 API 기반 차트 + 워드클라우드(WordCloud2)
 **********************************************************/
document.addEventListener("DOMContentLoaded", async function () {
  const cfg = getAuthorConfig();
  const authorId = cfg.id;
  if (!authorId) return;

  try {
    // 같은 API 응답으로 차트 + 워드클라우드 생성
    const limit = 100;
    const res = await fetch(`/author/api/${authorId}/?max_words=${limit}`);
    const data = await res.json();

    // --- (1) 연도별 출판 논문 ---
    const yLabels = Object.keys(data.year_chart_data || {});
    const yValues = Object.values(data.year_chart_data || {});
    renderBarChart("yearChart", yLabels, yValues, "#2E86AB");

    // --- (2) 파트별 논문 ---
    const pLabels = Object.keys(data.part_chart_data || {});
    const pValues = Object.values(data.part_chart_data || {});
    renderBarChart("partChart", pLabels, pValues, "#F6A01A");

    // --- (3) 워드클라우드(WordCloud2 사용, 메인 페이지와 동일 느낌) ---
    const wordsDict = data.keyword_data || {};
    const words = Object.entries(wordsDict).map(([text, size]) => [text, size]);

    let target = document.getElementById("author-wordcloud");
    if (!target || !window.WordCloud) return;

    // svg가 있다면 canvas로 교체
    if (target.tagName.toLowerCase() !== "canvas") {
      const parent = target.parentElement;
      const box = target.getBoundingClientRect();
      const canvas = document.createElement("canvas");
      canvas.id = "author-wordcloud";
      canvas.width = Math.max(260, Math.floor(box.width || 400));
      canvas.height = Math.max(260, Math.floor(box.height || 320));
      parent.replaceChild(canvas, target);
      target = canvas;
    } else {
      const box = target.getBoundingClientRect();
      target.width = Math.max(260, Math.floor(box.width || 400));
      target.height = Math.max(260, Math.floor(box.height || 320));
    }

    const vividColors = [
      "#1f77b4",
      "#ff7f0e",
      "#2ca02c",
      "#d62728",
      "#9467bd",
      "#8c564b",
      "#e377c2",
      "#7f7f7f",
      "#bcbd22",
      "#17becf",
    ];

    const maxVal = Math.max(...words.map((w) => w[1] || 1), 1);
    const baseW = Math.max(target.width, 320);
    const baseH = Math.max(target.height, 320);
    const scaleK = Math.sqrt((baseW * baseH) / (400 * 320));

    WordCloud(target, {
      list: words,
      gridSize: 8,
      weightFactor: (w) =>
        Math.max(12, (w / maxVal) * 42 * scaleK),
      fontFamily: "Noto Sans KR, Roboto, sans-serif",
      fontWeight: "700",
      minSize: 12,
      rotateRatio: 0.2,
      rotationSteps: 2,
      shuffle: true,
      shape: "circle",
      color: () =>
        vividColors[Math.floor(Math.random() * vividColors.length)],
      backgroundColor: "rgba(255,255,255,0)",

      click: function (item) {
        const word = item && item[0];
        if (!word) return;
        fetch(`/get_keyword_id/?name=${encodeURIComponent(word)}`)
          .then((r) => r.json())
          .then((j) =>
            j.keyword_id
              ? (window.location.href = `/keyword/${j.keyword_id}/`)
              : alert("해당 키워드 페이지를 찾을 수 없습니다."),
          );
      },

      drawOutOfBound: false,
      wait: 50,
      hover: null,
    });

    let wcRaf = null;
    window.addEventListener("resize", () => {
      cancelAnimationFrame(wcRaf);
      wcRaf = requestAnimationFrame(() => {
        const box = target.getBoundingClientRect();
        target.width = Math.max(260, Math.floor(box.width || 400));
        target.height = Math.max(260, Math.floor(box.height || 320));
        WordCloud.stop();
        WordCloud(target, {
          list: words,
          gridSize: 8,
          weightFactor: (w) =>
            Math.max(
              12,
              (w / maxVal) *
                42 *
                Math.sqrt((target.width * target.height) / (400 * 320)),
            ),
          fontFamily: "Noto Sans KR, Roboto, sans-serif",
          fontWeight: "700",
          minSize: 12,
          rotateRatio: 0.2,
          rotationSteps: 2,
          shuffle: true,
          shape: "circle",
          color: () =>
            vividColors[Math.floor(Math.random() * vividColors.length)],
          backgroundColor: "rgba(255,255,255,0)",
          click: function (item) {
            const word = item && item[0];
            if (!word) return;
            fetch(`/get_keyword_id/?name=${encodeURIComponent(word)}`)
              .then((r) => r.json())
              .then((j) =>
                j.keyword_id
                  ? (window.location.href = `/keyword/${j.keyword_id}/`)
                  : alert("해당 키워드 페이지를 찾을 수 없습니다."),
              );
          },
        });
      });
    });
  } catch (e) {
    console.error("author charts/wordcloud error:", e);
  }
});

/**********************************************************
 * 4. 공동 저자 네트워크(d3)
 **********************************************************/
document.addEventListener("DOMContentLoaded", () => {
  const cfg = getAuthorConfig();
  const authorId = cfg.id;
  const authorName = cfg.name;
  if (!authorId || !authorName || !window.d3) return;

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

  let resizeTimer = null;
  window.addEventListener("resize", () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(render, 120);
  });

  render();

  const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));

  function measureText(svg, text, fontSize = 18, fontWeight = 800, fontFamily = "inherit") {
    const ghost = svg
      .append("text")
      .attr("x", -9999)
      .attr("y", -9999)
      .attr("font-size", fontSize)
      .attr("font-weight", fontWeight)
      .attr("font-family", fontFamily)
      .text(text);
    const w = ghost.node().getBBox().width;
    ghost.remove();
    return w;
  }

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

  async function render() {
    const res = await fetch(`/author/api/${authorId}/`);
    const data = await res.json();
    const children = (data.network_data || []).slice(0, 15).map((d) => ({
      ...d,
      pubs: d.pubs ?? d.publication_count ?? d.paper_count ?? 0,
    }));

    const svg = d3.select("#networkChart").attr("preserveAspectRatio", "xMidYMid meet");
    if (!svg.node()) return;

    svg.selectAll("*").remove();

    const box = svg.node().getBoundingClientRect();
    const W = Math.max(560, box.width || 600);
    const H = Math.max(420, box.height || 420);
    svg.attr("viewBox", `0 0 ${W} ${H}`);

    const cx = W / 2,
      cy = H / 2;
    const edgeMargin = 24;
    const maxR = Math.min(W, H) / 2 - (edgeMargin + 32);

    const counts = children.map((d) => +d.count);
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

    const mainFontSize = 14;
    const mainFontWeight = 600;
    const textWidth = measureText(svg, authorName, mainFontSize, mainFontWeight);
    const paddingX = 28;
    const paddingY = 16;

    let mainW = clamp(textWidth + paddingX * 2, 130, W * 0.85);
    let mainH = clamp(mainFontSize + paddingY * 2, 50, H * 0.3);

    const nodes = [];
    const mainNode = {
      id: authorId,
      name: authorName,
      type: "main",
      x: cx,
      y: cy,
      mainW,
      mainH,
    };
    nodes.push(mainNode);

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
      const a =
        i * baseStep -
        Math.PI / 2 +
        (Math.random() - 0.5) * angleJitterScale;
      const inward = inwardScale(d.count || 0);
      let baseRad = i % 2 === 0 ? longBase : shortBase;
      if (i % 4 === 0) baseRad = userMaxR;

      const r = clamp(baseRad + randN() + fineJ() - inward, minRing, userMaxR);

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
      source: authorId,
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
        const p = edgePointOnRect(
          mainNode.x,
          mainNode.y,
          ch,
          mainW / 2,
          mainH / 2,
        );
        return p.x;
      })
      .attr("y1", (d) => {
        const ch = nodes.find((n) => n.id === d.target);
        const p = edgePointOnRect(
          mainNode.x,
          mainNode.y,
          ch,
          mainW / 2,
          mainH / 2,
        );
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
      .text((d) => d.name);

    const gChild = gNodes.filter((d) => d.type === "child");
    gChild
      .append("circle")
      .attr("r", (d) => d.r)
      .attr("fill", PALETTE.childFill)
      .attr("stroke", PALETTE.childStroke)
      .attr("stroke-width", 2)
      .style("cursor", "pointer")
      .on("click", (e, d) =>
        d.id ? (window.location.href = `/author/${d.id}/`) : null,
      )
      .on("mouseenter", function (e, d) {
        d3.select(this).attr("stroke-width", 3).attr("stroke", PALETTE.hover);
        linkSel
          .filter((l) => l.target === d.id)
          .attr("stroke", PALETTE.linkHigh)
          .attr("stroke-width", linkWidth(d.count) + 2);
        tip.html(tooltipHtml(d)).style("display", "block");
      })
      .on("mousemove", (e) =>
        tip
          .style("left", e.pageX + 12 + "px")
          .style("top", e.pageY - 18 + "px"),
      )
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
              <div>논문 수: <b>${d.pubs}</b></div>
              <div>공동 연구 횟수: <b>${d.count}</b></div>`;
    }
  }
});

/**********************************************************
 * 5. 논문 저장(내 서재 담기)
 **********************************************************/
document.addEventListener("DOMContentLoaded", async function () {
  const cfg = getAuthorConfig();
  const authorId = cfg.id;
  const saveButton = document.querySelector(".save-selected-papers");
  if (!authorId || !saveButton) return;

  try {
    const response = await fetch(`/author/api/${authorId}/`);
    const data = await response.json();

    if (data.error) {
      console.error("❌ 저장된 논문 조회 실패:", data.error);
      return;
    }

    const savedPaperIds = new Set(data.saved_paper_ids || []);

    saveButton.addEventListener("click", async function () {
      const selectedPapers = [];
      document
        .querySelectorAll("input[name='selected_papers']:checked")
        .forEach((checkbox) => {
          const paperId = checkbox.getAttribute("data-paper-id") || checkbox.value;
          if (paperId && !savedPaperIds.has(parseInt(paperId))) {
            selectedPapers.push(paperId);
          }
        });

      if (selectedPapers.length === 0) {
        alert("⚠️ 이미 저장된 논문을 제외한 새 논문이 없습니다.");
        return;
      }

      fetch("/author/save_paper/", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": cfg.csrfToken || getCookie("csrftoken"),
        },
        body: JSON.stringify({ paper_ids: selectedPapers }),
      })
        .then((response) => response.json())
        .then((data) => {
          if (data.message) {
            alert("✅ 선택한 논문이 저장되었습니다!");
          } else {
            alert("⚠ 논문 저장 실패: " + data.error);
          }
        })
        .catch((error) => console.error("⚠ 요청 실패:", error));
    });
  } catch (error) {
    console.error("❌ 저장된 논문 목록을 불러오는 중 오류 발생:", error);
  }
});

/**********************************************************
 * 6. 저자 좋아요 버튼
 **********************************************************/
document.addEventListener("DOMContentLoaded", function () {
  document.body.addEventListener("click", function (event) {
    if (!event.target.classList.contains("like-author")) return;

    const authorId = event.target.getAttribute("data-author-id");
    const likeButton = event.target;

    console.log(`🔥 좋아요 버튼 클릭됨! 저자 ID: ${authorId}`);

    fetch(`/author/like_author/${authorId}/`, {
      method: "POST",
      headers: {
        "X-CSRFToken": getCookie("csrftoken"),
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
        const text =
          data.liked
            ? `❤️ 좋아요 (<span id="like-count-${authorId}">${data.count}</span>)`
            : `🤍 좋아요 (<span id="like-count-${authorId}">${data.count}</span>)`;
        likeButton.innerHTML = text;
        likeButton.classList.toggle("btn-danger", data.liked);
        likeButton.classList.toggle("btn-outline-danger", !data.liked);
      })
      .catch((error) => console.error("⚠ AJAX 요청 오류:", error));
  });
});

/**********************************************************
 * 7. 정성적 분석(ollama) 토글
 **********************************************************/
document.addEventListener("DOMContentLoaded", function () {
  const analysisButton = document.getElementById("analysisToggle");
  const loginRedirectButton = document.getElementById("loginRedirect");
  const analysisContent = document.getElementById("analysisContent");
  const analysisResult = document.getElementById("analysisResult");
  const loadingMessage = document.getElementById("loadingMessage");
  const cfg = getAuthorConfig();
  const authorId = cfg.id || "0";

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
      if (open && !analysisResult.innerHTML.trim()) fetchOllamaAuthorAnalysis();
    });
  }

  function injectOnce(css, id = "ana-style") {
    const old = document.getElementById(id);
    if (old) old.remove();
    const style = document.createElement("style");
    style.id = id;
    style.textContent = css;
    document.head.appendChild(style);
  }

  function fetchOllamaAuthorAnalysis() {
    if (!authorId || authorId === "0") return;

    loadingMessage.style.display = "block";

    fetch(`/author/api/analyze_author/${authorId}/`, {
      method: "POST",
      headers: {
        "X-CSRFToken": cfg.csrfToken || getCookie("csrftoken"),
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
});

/**********************************************************
 * 8. 페이지네이션 (동적 버튼 생성)
 **********************************************************/
document.addEventListener("DOMContentLoaded", function () {
  const paginationControls = document.getElementById("paginationControls");
  if (!paginationControls) return;

  const cfg = getAuthorConfig();
  const currentPage = Number(cfg.currentPage || 1);
  const totalPages = Number(cfg.totalPages || 1);
  const itemsPerPage = cfg.itemsPerPage || "";

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
        const goto = parseInt(btn.getAttribute("data-page"), 10);
        if (!isNaN(goto) && goto >= 1 && goto <= total && goto !== cur) {
          const nextUrl = new URL(window.location);
          nextUrl.searchParams.set("page", goto);
          if (itemsPerPage !== "") {
            nextUrl.searchParams.set("items_per_page", itemsPerPage);
          }
          window.location.href = nextUrl.toString();
        }
      });
    });
  }

  renderPagination(currentPage, totalPages);
});
