/* ============================================================
   0) 공용 함수: CSRF 쿠키 가져오기
============================================================ */
function getCookie(name) {
    const cookies = document.cookie.split(";").map(c => c.trim());
    for (const cookie of cookies) {
        if (cookie.startsWith(name + "=")) {
            return decodeURIComponent(cookie.substring(name.length + 1));
        }
    }
    return null;
}


/* ============================================================
   1) PDF 저장 기능
============================================================ */
document.addEventListener("DOMContentLoaded", function () {
    const pdfBtn = document.getElementById("pdfDownload");
    if (!pdfBtn) return;

    pdfBtn.addEventListener("click", function () {
        if (!confirm("📄 PDF를 다운로드 하시겠습니까?")) return;

        html2canvas(document.body, {
            scale: 2,
            useCORS: true,
            allowTaint: true
        }).then(canvas => {

            const imgData = canvas.toDataURL("image/png");
            const pdf = new jspdf.jsPDF("p", "mm", "a4");

            const imgWidth = 210;
            const imgHeight = (canvas.height * imgWidth) / canvas.width;

            pdf.addImage(imgData, "PNG", 0, 0, imgWidth, imgHeight);

            const contentType = window.contentType;
            const objectId = window.objectId;
            const objectTitle = window.objectTitle.replace(/[/\\?%*:|"<>]/g, "");
            const fileName = `${contentType}_${objectTitle}.pdf`;

            const formData = new FormData();
            formData.append("pdf", pdf.output("blob"), fileName);
            formData.append("content_type", contentType);
            formData.append("object_id", objectId);
            formData.append("object_title", objectTitle);

            fetch("/paper/pdf_upload/", {
                method: "POST",
                body: formData,
                headers: { "X-CSRFToken": window.csrfToken }
            })
                .then(res => res.json())
                .then(data => {
                    if (data.success) pdf.save(fileName);
                    else alert("⚠ 오류: " + data.error);
                });
        });
    });
});


/* ============================================================
   2) 최근 본 논문 저장
============================================================ */
document.addEventListener("DOMContentLoaded", function () {
    if (!window.paperId) return;

    fetch(`/paper/save_recent_paper/${window.paperId}/`)
        .then(res => res.json())
        .catch(console.error);
});


/* ============================================================
   3) 좋아요 기능
============================================================ */
document.addEventListener("click", function (event) {
    if (!event.target.classList.contains("like-paper")) return;

    const btn = event.target;
    const paperId = btn.dataset.paperId;

    fetch(`/paper/like_paper/${paperId}/`, {
        method: "POST",
        headers: {
            "X-CSRFToken": getCookie("csrftoken"),
            "Content-Type": "application/json"
        }
    })
        .then(res => res.json())
        .then(data => {
            btn.classList.toggle("active", data.liked);
            btn.innerHTML = `${data.liked ? "❤️" : "🤍"} 좋아요 (<span id="like-count-${paperId}">${data.count}</span>)`;
        })
        .catch(console.error);
});


/* ============================================================
   4) 내 서재 저장 (단일 + 다중)
============================================================ */
document.addEventListener("DOMContentLoaded", async function () {

    const saveSelectedBtn = document.querySelector(".save-selected-papers");
    const saveOneBtn = document.getElementById("save-paper-btn");

    const saved = await fetch("/paper/get_saved_papers/").then(r => r.json());
    const savedIds = new Set(saved.saved_paper_ids || []);

    function savePapers(list) {
        fetch("/paper/save_paper/", {
            method: "POST",
            headers: {
                "X-CSRFToken": getCookie("csrftoken"),
                "Content-Type": "application/json"
            },
            body: JSON.stringify({ paper_ids: list })
        })
            .then(r => r.json())
            .then(d => alert(d.message || d.error))
            .catch(console.error);
    }

    if (saveOneBtn) {
        saveOneBtn.addEventListener("click", () => {
            if (savedIds.has(Number(window.paperId))) {
                alert("⚠ 이미 저장된 논문입니다.");
                return;
            }
            savePapers([window.paperId]);
        });
    }

    if (saveSelectedBtn) {
        saveSelectedBtn.addEventListener("click", () => {
            const selected = [...document.querySelectorAll(".selected-paper:checked")]
                .map(x => Number(x.dataset.paperId))
                .filter(x => !savedIds.has(x));

            if (!selected.length) {
                alert("⚠ 새로 저장할 논문이 없습니다.");
                return;
            }

            savePapers(selected);
        });
    }
});


/* ============================================================
   5) 페이지네이션
============================================================ */
document.addEventListener("DOMContentLoaded", function () {
    const controlBox = document.getElementById("paginationControls");
    if (!controlBox) return;

    const currentPage = window.currentPage;
    const totalPages = window.totalPages;

    function renderPagination() {
        let html = `<div class="pagination">`;

        const max = 7;
        const half = Math.floor(max / 2);

        let start = Math.max(1, currentPage - half);
        let end = Math.min(totalPages, start + max - 1);

        if (end - start + 1 < max) start = Math.max(1, end - max + 1);

        function btn(page, label, enabled) {
            return `<button class="page-btn" data-page="${page}" ${enabled ? "" : "disabled"}>${label}</button>`;
        }

        html += btn(1, "« 처음", currentPage > 1);
        html += btn(currentPage - 1, "‹ 이전", currentPage > 1);

        for (let i = start; i <= end; i++) {
            html += `<button class="page-btn ${i === currentPage ? "active" : ""}" data-page="${i}">${i}</button>`;
        }

        html += btn(currentPage + 1, "다음 ›", currentPage < totalPages);
        html += btn(totalPages, "마지막 »", currentPage < totalPages);

        html += `</div>`;
        controlBox.innerHTML = html;

        controlBox.querySelectorAll(".page-btn").forEach(button => {
            button.addEventListener("click", () => {
                const p = Number(button.dataset.page);
                if (!p || p === currentPage) return;

                const url = new URL(window.location.href);
                url.searchParams.set("page", p);
                window.location.href = url.toString();
            });
        });
    }

    renderPagination();
});


/* ============================================================
   6) 저자 더보기 버튼
============================================================ */
document.addEventListener("DOMContentLoaded", function () {
    const moreBox = document.getElementById("authorListMore");
    const toggleBtn = document.getElementById("toggleAuthors");

    if (!moreBox || !toggleBtn) return;

    toggleBtn.addEventListener("click", () => {
        const hidden = moreBox.style.display !== "block";
        moreBox.style.display = hidden ? "block" : "none";

        toggleBtn.classList.toggle("expanded", hidden);
        toggleBtn.querySelector(".label").textContent = hidden ? "접기" : "더보기";
    });
});
