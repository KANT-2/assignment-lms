/* 강의 및 교안 관리 (tutor/lecture_manage.html) 전용 스크립트.
   원래 템플릿 <script> 인라인 블록에서 분리.
   Django 값은 템플릿의 json_script 블록(#lecture-lessons-data 등)에서 읽는다. */

(function () {
  "use strict";

  const readJson = (id) => JSON.parse(document.getElementById(id).textContent);

  let lessons = readJson("lecture-lessons-data");
  let lectureRevision = readJson("lecture-revision-data");
  const csrfToken = readJson("csrf-token-data");
  let currentTab = "all";
  let deletedLessonBackup = null;

  window.toggleRows = function (dateStr) {
    const rows = document.querySelectorAll(`.child-row-${dateStr}`);
    rows.forEach((r) => {
      if (r.style.display === "none") {
        r.style.display = "table-row";
      } else {
        r.style.display = "none";
      }
    });
  };

  function loadLessons() {
    lessons.sort((a, b) => (a.date || "").localeCompare(b.date || ""));
    renderTable();
  }

  function saveToStorage() {
    return fetch("/tutor/lecture/api/update/", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrfToken,
      },
      body: JSON.stringify({ lessons: lessons, base_revision: lectureRevision }),
    })
      .then((res) => res.json().then((data) => ({ status: res.status, data })))
      .then(({ status, data }) => {
        if (data.status === "success") {
          // 서버가 매긴 정식 id·순서로 클라이언트 상태를 교체 → 다음 저장에 임시 id가 안 섞인다
          lessons = data.lessons;
          lectureRevision = data.revision;
          renderTable();
          return true;
        }
        if (status === 409 || data.status === "stale") {
          lessons = data.lessons || lessons;
          lectureRevision = data.revision || lectureRevision;
          renderTable();
          showToast(data.detail || "다른 곳에서 변경되어 최신 내용으로 되돌렸습니다.");
          return false;
        }
        console.error("Save failed", data);
        showToast("저장에 실패했습니다. 잠시 후 다시 시도해 주세요.");
        return false;
      })
      .catch((e) => {
        console.error("Error saving:", e);
        showToast("저장 중 오류가 발생했습니다.");
        return false;
      });
  }

  // Helper to extract YouTube ID & Thumbnail
  function getYouTubeId(url) {
    if (!url) return null;
    const match = url.match(
      /(?:youtu\.be\/|youtube\.com\/(?:embed\/|v\/|watch\?v=|watch\?.+&v=))([\w-]{11})/
    );
    return match ? match[1] : null;
  }

  function getYouTubeThumbnail(url) {
    const id = getYouTubeId(url);
    return id ? `https://img.youtube.com/vi/${id}/mqdefault.jpg` : null;
  }

  function renderTable() {
    const tbody = document.getElementById("lesson-table-body");
    tbody.innerHTML = "";

    const query = document.getElementById("search-input").value.trim().toLowerCase();

    const filtered = lessons.filter((l) => {
      const hasVideo = l.videos && l.videos.length > 0;
      // Tab filter
      if (currentTab === "video-ok" && !hasVideo) return false;
      if (currentTab === "video-wait" && hasVideo) return false;
      // Search filter
      if (query) {
        return (
          l.title.toLowerCase().includes(query) ||
          l.date.includes(query)
        );
      }
      return true;
    });

    if (filtered.length === 0) {
      tbody.innerHTML = `<tr><td colspan="5" style="text-align:center; padding: 36px; color: var(--text-muted);">조건에 맞는 차시가 없습니다.</td></tr>`;
      return;
    }

    // Sort by date (descending)
    filtered.sort((a, b) => new Date(b.date) - new Date(a.date));

    const dateSpans = {};
    filtered.forEach((lesson) => {
      dateSpans[lesson.date] = (dateSpans[lesson.date] || 0) + 1;
    });

    let renderedDates = {};
    let dailyIndex = {};

    filtered.forEach((lesson) => {
      const tr = document.createElement("tr");

      // Video Status & Thumbnail (uses videos array now)
      const firstVideo = lesson.videos && lesson.videos.length > 0 ? lesson.videos[0] : null;
      const thumbUrl = firstVideo ? getYouTubeThumbnail(firstVideo.url) : null;
      let videoCellHtml = "";

      if (thumbUrl) {
        const videoCount = lesson.videos.length;
        videoCellHtml = `
          <div class="video-cell">
            <div class="table-thumb" title="유튜브 썸네일">
              <img src="${thumbUrl}" alt="썸네일" loading="lazy">
            </div>
            <span class="badge video-ok">등록 완료${videoCount > 1 ? ` (${videoCount}개)` : ""}</span>
          </div>
        `;
      } else {
        videoCellHtml = `
          <div class="video-cell">
            <div class="table-thumb-none">미등록</div>
            <span class="badge video-wait">영상 대기</span>
          </div>
        `;
      }

      // Blog status
      const blogHtml =
        lesson.blogUrl && lesson.blogUrl.trim()
          ? `<a href="${lesson.blogUrl}" target="_blank" style="color:var(--accent-text); font-weight:600; text-decoration:underline;">링크</a>`
          : `<span style="color:var(--text-faint);">-</span>`;

      // Material chip
      const matCount = lesson.materials ? lesson.materials.length : 0;
      const matHtml =
        matCount > 0
          ? `<span class="badge mat-chip">${matCount}건</span>`
          : `<span style="color:var(--text-faint); font-size:12px;">없음</span>`;

      let dateCellHtml = "";
      const span = dateSpans[lesson.date];

      if (!renderedDates[lesson.date]) {
        let toggleBtn = "";
        if (span > 1) {
          toggleBtn = `<br><button class="btn btn-sm btn-outline" style="margin-top: 8px; font-size: 11px; padding: 4px 8px; color: var(--accent-text);" onclick="toggleRows('${lesson.date}')">▼ ${span - 1}개 더보기</button>`;
        }
        dateCellHtml = `<td style="color:var(--text); font-size:13px; font-weight:800; border-right:1px solid var(--border); text-align:center; vertical-align:middle; background:#f8fafc;">${lesson.date} ${toggleBtn}</td>`;
        renderedDates[lesson.date] = true;
        dailyIndex[lesson.date] = 1;
      } else {
        dailyIndex[lesson.date]++;
        dateCellHtml = `<td style="border-right:1px solid var(--border); background:#fcfcfc; text-align:center;"><span style="color:var(--border-strong);">↳</span></td>`;
      }

      const currentDailyIndex = dailyIndex[lesson.date];

      const rowClass = currentDailyIndex > 1 ? `child-row-${lesson.date}` : "";
      const displayStyle = currentDailyIndex > 1 ? "display: none;" : "";

      tr.className = rowClass;
      tr.style.cssText = displayStyle;

      tr.innerHTML = `
        ${dateCellHtml}

        <td>
          <span style="font-weight:700; color:var(--text);">${lesson.title}</span>
        </td>
        <td>${matHtml}</td>
        <td>${videoCellHtml}</td>
        <td style="text-align: right;">
          <div class="action-group" style="justify-content: flex-end;">
            <button class="btn btn-outline btn-sm" onclick="openEditModal(${lesson.id})">수정</button>
            <button class="btn btn-danger btn-sm" onclick="deleteLesson(${lesson.id})">삭제</button>
          </div>
        </td>
      `;
      tbody.appendChild(tr);
    });
  }

  function setTab(tab, btn) {
    currentTab = tab;
    document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    renderTable();
  }

  function filterLessons() {
    renderTable();
  }

  // Modal handlers
  function openCreateModal() {
    document.getElementById("modal-title").textContent = "새 일정 등록";
    document.getElementById("edit-lesson-id").value = "";
    document.getElementById("form-date").value = new Date().toISOString().slice(0, 10);
    document.getElementById("form-title").value = "";
    
    document.getElementById("video-builder-list").innerHTML = "";
    addVideoRow("", "");
    
    document.getElementById("material-builder-list").innerHTML = "";
    addMaterialRow("FILE", "", "");

    openModal("lesson-modal");
  }

  function openEditModal(id) {
    const lesson = lessons.find((l) => l.id === id);
    if (!lesson) return;

    document.getElementById("modal-title").textContent = `일정 수정`;
    document.getElementById("edit-lesson-id").value = lesson.id;
    document.getElementById("form-date").value = lesson.date;
    document.getElementById("form-title").value = lesson.title;

    const vidList = document.getElementById("video-builder-list");
    vidList.innerHTML = "";
    if (lesson.videos && lesson.videos.length > 0) {
      lesson.videos.forEach((v) => addVideoRow(v.title, v.url));
    } else {
      addVideoRow("", "");
    }

    const matList = document.getElementById("material-builder-list");
    matList.innerHTML = "";
    if (lesson.materials && lesson.materials.length > 0) {
      lesson.materials.forEach((m) => addMaterialRow(m.kind, m.title, m.url));
    } else {
      addMaterialRow("FILE", "", "");
    }

    openModal("lesson-modal");
  }

  window.addVideoRow = function(title = "", url = "") {
    const list = document.getElementById("video-builder-list");
    const rowId = "vid-" + Math.random().toString(36).substr(2, 9);
    const row = document.createElement("div");
    row.className = "video-row";
    row.style.cssText = "border:1px solid var(--border); border-radius:8px; padding:12px; margin-bottom:12px; background:#fafafa; position:relative;";
    
    row.innerHTML = `
      <div style="display:flex; gap:8px; margin-bottom:8px;">
        <input type="text" class="form-control vid-title" placeholder="영상 제목 (예: 1부 개념)" value="${title}" style="flex:1;">
        <input type="url" class="form-control vid-url" placeholder="유튜브 URL (https://...)" value="${url}" style="flex:2;" oninput="updateVideoPreview('${rowId}', this.value)">
      </div>
      
      <!-- Live Preview -->
      <div id="video-preview-${rowId}" class="video-preview-wrap" style="display:none; margin-top:8px;">
        <div class="preview-media-container" style="gap:8px; display:flex;">
          <div class="preview-box" style="flex:1;">
            <img id="video-thumb-preview-${rowId}" src="" alt="유튜브 썸네일" style="width:100%; border-radius:4px;">
          </div>
          <div class="preview-box" style="flex:2;">
            <iframe id="video-preview-iframe-${rowId}" src="" style="width:100%; aspect-ratio:16/9; border:none; border-radius:4px;" referrerpolicy="strict-origin-when-cross-origin" allowfullscreen></iframe>
          </div>
        </div>
      </div>

      <button type="button" class="material-row-del" onclick="this.parentElement.remove()" style="position:absolute; top:-10px; right:-10px; background:var(--surface); border:1px solid var(--border); border-radius:50%; width:24px; height:24px; display:flex; align-items:center; justify-content:center; cursor:pointer;" title="삭제">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
      </button>
    `;
    list.appendChild(row);
    if(url) {
      setTimeout(() => window.updateVideoPreview(rowId, url), 50);
    }
  }

  window.updateVideoPreview = function(rowId, url) {
    const box = document.getElementById("video-preview-" + rowId);
    const iframe = document.getElementById("video-preview-iframe-" + rowId);
    const thumbImg = document.getElementById("video-thumb-preview-" + rowId);

    const match = url.match(/(?:youtu\.be\/|youtube\.com\/(?:embed\/|v\/|watch\?v=|watch\?.+&v=))([\w-]{11})/);
    const vId = match ? match[1] : null;

    if (vId) {
      box.style.display = "block";
      const originParam = window.location.protocol === "file:" ? "?origin=http://localhost" : `?origin=${encodeURIComponent(window.location.origin)}`;
      iframe.src = `https://www.youtube-nocookie.com/embed/${vId}${originParam}`;
      thumbImg.src = `https://img.youtube.com/vi/${vId}/mqdefault.jpg`;
    } else {
      box.style.display = "none";
      iframe.src = "";
      thumbImg.src = "";
    }
  }

  function addMaterialRow(kind = "FILE", title = "", url = "") {
    const list = document.getElementById("material-builder-list");
    const row = document.createElement("div");
    row.className = "material-row";

    // UUID for input ID matching
    const rowId = "mat-" + Math.random().toString(36).substr(2, 9);

    row.innerHTML = `
      <select class="form-control mat-kind" style="padding: 6px 8px; font-size:12px;" onchange="toggleMaterialInput(this, '${rowId}')">
        <option value="FILE" ${kind === "FILE" ? "selected" : ""}>내 PC 파일</option>
        <option value="LINK" ${kind === "LINK" ? "selected" : ""}>외부 링크</option>
      </select>
      <input type="text" class="form-control mat-title" placeholder="자료명 (예: 1주차 교안)" value="${title}" style="padding: 6px 8px; font-size:12px;">

      <div id="wrap-file-${rowId}" style="display: ${kind === "FILE" ? "block" : "none"};">
        <input type="hidden" class="mat-existing-url" value="${kind === "FILE" ? url : ""}">
        <input type="file" class="form-control mat-file" style="padding: 4px 8px; font-size:12px;" ${kind === "FILE" ? "" : "disabled"}>
        ${kind === "FILE" && url ? `<div style="font-size:10px; color:var(--text-muted); margin-top:4px;">현재 파일: ${url}</div>` : ""}
      </div>
      <div id="wrap-url-${rowId}" style="display: ${kind === "LINK" ? "block" : "none"};">
        <input type="text" class="form-control mat-url" placeholder="https://..." value="${url}" style="padding: 6px 8px; font-size:12px;" ${kind === "LINK" ? "" : "disabled"}>
      </div>

      <button type="button" class="material-row-del" onclick="this.parentElement.remove()" title="삭제">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
      </button>
    `;
    list.appendChild(row);
  }

  function toggleMaterialInput(selectEl, rowId) {
    const kind = selectEl.value;
    const wrapFile = document.getElementById("wrap-file-" + rowId);
    const wrapUrl = document.getElementById("wrap-url-" + rowId);
    const inputFile = wrapFile.querySelector(".mat-file");
    const inputUrl = wrapUrl.querySelector(".mat-url");

    if (kind === "FILE") {
      wrapFile.style.display = "block";
      wrapUrl.style.display = "none";
      inputFile.disabled = false;
      inputUrl.disabled = true;
    } else {
      wrapFile.style.display = "none";
      wrapUrl.style.display = "block";
      inputFile.disabled = true;
      inputUrl.disabled = false;
    }
  }

    function saveLesson() {
    const title = document.getElementById("form-title").value.trim();
    const date = document.getElementById("form-date").value;
    const editId = document.getElementById("edit-lesson-id").value;

    if (!title || !date) {
      alert("수업 제목과 수업 일자를 입력해주세요.");
      return;
    }

    // Collect videos from video-builder-list
    const videos = [];
    document.querySelectorAll("#video-builder-list .video-row").forEach((row) => {
      const vTitle = (row.querySelector(".vid-title") ? row.querySelector(".vid-title").value.trim() : "");
      const vUrl = (row.querySelector(".vid-url") ? row.querySelector(".vid-url").value.trim() : "");
      if (vUrl) videos.push({ title: vTitle, url: vUrl });
    });

    // Collect materials
    const materials = [];
    document.querySelectorAll("#material-builder-list .material-row").forEach((row) => {
      const kind = row.querySelector(".mat-kind").value;
      let matTitle = row.querySelector(".mat-title").value.trim();
      let matUrl = "";
      let matSize = "";

      if (kind === "FILE") {
        const fileInput = row.querySelector(".mat-file");
        if (fileInput && fileInput.files && fileInput.files.length > 0) {
          const file = fileInput.files[0];
          matUrl = file.name;
          matSize = (file.size / 1024 / 1024).toFixed(1) + " MB";
          if (!matTitle) matTitle = file.name;
        } else {
          const existingUrlInput = row.querySelector(".mat-existing-url");
          if (existingUrlInput && existingUrlInput.value) {
            matUrl = existingUrlInput.value;
            matSize = "기존 파일";
            if (!matTitle) matTitle = matUrl;
          } else {
            matUrl = "#";
          }
        }
      } else {
        matUrl = row.querySelector(".mat-url").value.trim() || "#";
        if (!matTitle && matUrl !== "#") matTitle = "외부 링크";
      }

      if (matTitle) {
        materials.push({ kind, title: matTitle, url: matUrl, size: matSize });
      }
    });

    if (editId) {
      // Update
      const idx = lessons.findIndex((l) => l.id === parseInt(editId));
      if (idx !== -1) {
        lessons[idx] = {
          ...lessons[idx],
          date,
          title,
          videos,
          materials,
        };
      }
      showToast(`${date} 수업 정보가 수정되었습니다.`);
    } else {
      // Create
      const newLesson = {
        id: Date.now(),
        date,
        title,
        videos,
        materials,
      };
      lessons.push(newLesson);
      showToast("새 일정이 등록되었습니다. (학생 화면 즉시 반영)");
    }

    lessons.sort((a, b) => (a.date || "").localeCompare(b.date || ""));

    // UI 우선 반영
    renderTable();
    closeModal("lesson-modal");

    // 서버 저장 및 DB ID로 갱신
    saveToStorage().catch((e) => {
      alert("저장에 실패했습니다.");
    });
  }

  

  // Delete & Undo
  function deleteLesson(id) {
    const idx = lessons.findIndex((l) => l.id === id);
    if (idx === -1) return;

    deletedLessonBackup = { index: idx, data: lessons[idx] };
    const dateStr = lessons[idx].date;
    lessons.splice(idx, 1);
    renderTable();
    saveToStorage().catch((e) => alert("삭제 저장에 실패했습니다."));

    showToast(`${dateStr} 일정이 삭제되었습니다.`, true);
  }

  function undoDelete() {
    if (deletedLessonBackup) {
      lessons.splice(deletedLessonBackup.index, 0, deletedLessonBackup.data);
      lessons.sort((a, b) => (a.date || "").localeCompare(b.date || ""));
      deletedLessonBackup = null;
      renderTable();
      saveToStorage().catch((e) => alert("복구 저장에 실패했습니다."));
      showToast("삭제가 취소되었습니다.");
    }
  }

  // Common Modal Controls
  function openModal(id) {
    document.getElementById(id).classList.add("show");
    document.body.classList.add("modal-open");
  }

  function closeModal(id) {
    document.getElementById(id).classList.remove("show");
    document.body.classList.remove("modal-open");
  }

  function handleBackdropClick(e, id) {
    if (e.target.id === id) {
      closeModal(id);
    }
  }

  // Toast
  let toastTimer = null;
  function showToast(msg, canUndo = false) {
    const toast = document.getElementById("toast");
    document.getElementById("toast-text").textContent = msg;
    const undoBtn = document.getElementById("toast-undo");
    undoBtn.style.display = canUndo ? "inline-block" : "none";

    toast.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => {
      toast.classList.remove("show");
    }, 3200);
  }

  // 템플릿 인라인 onclick / oninput 에서 참조하는 함수들을 전역으로 노출
  Object.assign(window, {
    setTab,
    filterLessons,
    openCreateModal,
    openEditModal,
    addMaterialRow,
    toggleMaterialInput,
    updateVideoPreview,
    saveLesson,
    deleteLesson,
    undoDelete,
    openModal,
    closeModal,
    handleBackdropClick,
  });

  // Init
  loadLessons();
})();
