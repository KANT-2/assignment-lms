

  let lessons = [];
const csrfToken = "test";
  let currentTab = 'all';
  let deletedLessonBackup = null;

  function loadLessons() {
    lessons.sort((a, b) => a.order - b.order);
    renderTable();
  }

  function saveToStorage() {
  fetch('/tutor/lecture/api/update/', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': csrfToken
    },
    body: JSON.stringify({lessons: lessons})
  }).then(res => res.json()).then(data => {
    if(data.status !== 'success') console.error('Save failed', data);
  }).catch(e => console.error('Error saving:', e));
} catch(e) {
      console.error('Storage error:', e);
    }
  }

  

  // Helper to extract YouTube ID & Thumbnail
  function getYouTubeId(url) {
    if (!url) return null;
    const match = url.match(/(?:youtu\.be\/|youtube\.com\/(?:embed\/|v\/|watch\?v=|watch\?.+&v=))([\w-]{11})/);
    return match ? match[1] : null;
  }

  function getYouTubeThumbnail(url) {
    const id = getYouTubeId(url);
    return id ? `https://img.youtube.com/vi/${id}/mqdefault.jpg` : null;
  }

  function renderTable() {
    const tbody = document.getElementById('lesson-table-body');
    tbody.innerHTML = '';

    const query = document.getElementById('search-input').value.trim().toLowerCase();

    const filtered = lessons.filter(l => {
      // Tab filter
      if (currentTab === 'video-ok' && !l.videoUrl) return false;
      if (currentTab === 'video-wait' && l.videoUrl) return false;
      // Search filter
      if (query) {
        return l.title.toLowerCase().includes(query) || l.date.includes(query) || `${l.order}회차`.includes(query);
      }
      return true;
    });

    if (filtered.length === 0) {
      tbody.innerHTML = `<tr><td colspan="7" style="text-align:center; padding: 36px; color: var(--text-muted);">조건에 맞는 차시가 없습니다.</td></tr>`;
      return;
    }

    filtered.forEach(lesson => {
      const tr = document.createElement('tr');

      // Video Status & Thumbnail
      const thumbUrl = getYouTubeThumbnail(lesson.videoUrl);
      let videoCellHtml = '';

      if (thumbUrl) {
        videoCellHtml = `
          <div class="video-cell">
            <div class="table-thumb" title="유튜브 썸네일">
              <img src="${thumbUrl}" alt="썸네일" loading="lazy">
            </div>
            <span class="badge video-ok">등록 완료</span>
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
      const blogHtml = (lesson.blogUrl && lesson.blogUrl.trim())
        ? `<a href="${lesson.blogUrl}" target="_blank" style="color:var(--accent-text); font-weight:600; text-decoration:underline;">링크</a>`
        : `<span style="color:var(--text-faint);">-</span>`;

      // Material chip
      const matCount = lesson.materials ? lesson.materials.length : 0;
      const matHtml = matCount > 0 
        ? `<span class="badge mat-chip">${matCount}건</span>` 
        : `<span style="color:var(--text-faint); font-size:12px;">없음</span>`;

      tr.innerHTML = `
        <td><span class="badge order">${lesson.order}회차</span></td>
        <td style="color:var(--text-muted); font-size:12.5px;">${lesson.date}</td>
        <td>
          <span style="font-weight:700; color:var(--text);">${lesson.title}</span>
        </td>
        <td>${matHtml}</td>
        <td>${videoCellHtml}</td>
        <td>${blogHtml}</td>
        <td style="text-align: right;">
          <div class="action-group" style="justify-content: flex-end;">
            ${!lesson.videoUrl 
              ? `<button class="btn btn-primary btn-sm" onclick="openQuickVideoModal(${lesson.id})">영상 등록</button>` 
              : `<button class="btn btn-outline btn-sm" onclick="openQuickVideoModal(${lesson.id})">영상 변경</button>`
            }
            <button class="btn btn-outline btn-sm" onclick="openEditModal(${lesson.id})">수정</button>
            <button class="btn btn-danger btn-sm" onclick="deleteLesson(${lesson.id})">삭제</button>
          </div>
        </td>
      `;
      tbody.appendChild(tr);
    });

    updateStats();
  }

  function updateStats() {
    const total = lessons.length;
    const videoOk = lessons.filter(l => !!l.videoUrl).length;
    const videoWait = lessons.filter(l => !l.videoUrl).length;
    let totalMat = 0;
    lessons.forEach(l => { totalMat += (l.materials ? l.materials.length : 0); });

    document.getElementById('stat-total').textContent = `${total}개`;
    document.getElementById('stat-video-ok').textContent = `${videoOk}개`;
    document.getElementById('stat-video-wait').textContent = `${videoWait}개`;
    document.getElementById('stat-materials').textContent = `${totalMat}건`;

    document.getElementById('tab-btn-ok').textContent = `영상 완료 (${videoOk})`;
    document.getElementById('tab-btn-wait').textContent = `영상 대기/미등록 (${videoWait})`;
  }

  function setTab(tab, btn) {
    currentTab = tab;
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    renderTable();
  }

  function filterLessons() {
    renderTable();
  }

  // Modal handlers
  function openCreateModal() {
    document.getElementById('modal-title').textContent = '새 차시 등록';
    document.getElementById('edit-lesson-id').value = '';
    document.getElementById('form-order').value = lessons.length + 1;
    document.getElementById('form-date').value = new Date().toISOString().slice(0, 10);
    document.getElementById('form-title').value = '';
    document.getElementById('form-blog').value = '';
    document.getElementById('form-video').value = '';
    document.getElementById('material-builder-list').innerHTML = '';
    addMaterialRow('FILE', '', '');

    updateVideoPreview();
    openModal('lesson-modal');
  }

  function openEditModal(id) {
    const lesson = lessons.find(l => l.id === id);
    if (!lesson) return;

    document.getElementById('modal-title').textContent = `${lesson.order}회차 수업 수정`;
    document.getElementById('edit-lesson-id').value = lesson.id;
    document.getElementById('form-order').value = lesson.order;
    document.getElementById('form-date').value = lesson.date;
    document.getElementById('form-title').value = lesson.title;
    document.getElementById('form-blog').value = lesson.blogUrl || '';
    document.getElementById('form-video').value = lesson.videoUrl || '';

    const matList = document.getElementById('material-builder-list');
    matList.innerHTML = '';
    if (lesson.materials && lesson.materials.length > 0) {
      lesson.materials.forEach(m => addMaterialRow(m.kind, m.title, m.url));
    } else {
      addMaterialRow('FILE', '', '');
    }

    updateVideoPreview();
    openModal('lesson-modal');
  }

  function addMaterialRow(kind = 'FILE', title = '', url = '') {
    const list = document.getElementById('material-builder-list');
    const row = document.createElement('div');
    row.className = 'material-row';
    
    // UUID for input ID matching
    const rowId = 'mat-' + Math.random().toString(36).substr(2, 9);
    
    row.innerHTML = `
      <select class="form-control mat-kind" style="padding: 6px 8px; font-size:12px;" onchange="toggleMaterialInput(this, '${rowId}')">
        <option value="FILE" ${kind === 'FILE' ? 'selected' : ''}>내 PC 파일</option>
        <option value="LINK" ${kind === 'LINK' ? 'selected' : ''}>외부 링크</option>
      </select>
      <input type="text" class="form-control mat-title" placeholder="자료명 (예: 1주차 교안)" value="${title}" style="padding: 6px 8px; font-size:12px;">
      
      <div id="wrap-file-${rowId}" style="display: ${kind === 'FILE' ? 'block' : 'none'};">
        <input type="file" class="form-control mat-file" style="padding: 4px 8px; font-size:12px;" ${kind === 'FILE' ? '' : 'disabled'}>
      </div>
      <div id="wrap-url-${rowId}" style="display: ${kind === 'LINK' ? 'block' : 'none'};">
        <input type="text" class="form-control mat-url" placeholder="https://..." value="${url}" style="padding: 6px 8px; font-size:12px;" ${kind === 'LINK' ? '' : 'disabled'}>
      </div>
      
      <button type="button" class="material-row-del" onclick="this.parentElement.remove()" title="삭제">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
      </button>
    `;
    list.appendChild(row);
  }

  function toggleMaterialInput(selectEl, rowId) {
    const kind = selectEl.value;
    const wrapFile = document.getElementById('wrap-file-' + rowId);
    const wrapUrl = document.getElementById('wrap-url-' + rowId);
    const inputFile = wrapFile.querySelector('.mat-file');
    const inputUrl = wrapUrl.querySelector('.mat-url');

    if (kind === 'FILE') {
      wrapFile.style.display = 'block';
      wrapUrl.style.display = 'none';
      inputFile.disabled = false;
      inputUrl.disabled = true;
    } else {
      wrapFile.style.display = 'none';
      wrapUrl.style.display = 'block';
      inputFile.disabled = true;
      inputUrl.disabled = false;
    }
  }

  function updateVideoPreview() {
    const url = document.getElementById('form-video').value.trim();
    const box = document.getElementById('video-preview');
    const iframe = document.getElementById('video-preview-iframe');
    const thumbImg = document.getElementById('video-thumb-preview');
    const idDisplay = document.getElementById('video-id-display');

    const vId = getYouTubeId(url);

    if (vId) {
      box.style.display = 'flex';
      const originParam = window.location.protocol === 'file:' ? '?origin=http://localhost' : `?origin=${encodeURIComponent(window.location.origin)}`;
      iframe.src = `https://www.youtube-nocookie.com/embed/${vId}${originParam}`;
      thumbImg.src = `https://img.youtube.com/vi/${vId}/mqdefault.jpg`;
      idDisplay.textContent = `Video ID: ${vId}`;
    } else {
      box.style.display = 'none';
      iframe.src = '';
      thumbImg.src = '';
    }
  }

  function saveLesson() {
    const title = document.getElementById('form-title').value.trim();
    const order = parseInt(document.getElementById('form-order').value) || 1;
    const date = document.getElementById('form-date').value;
    const blogUrl = document.getElementById('form-blog').value.trim() || null;
    const videoUrl = document.getElementById('form-video').value.trim() || null;
    const editId = document.getElementById('edit-lesson-id').value;

    if (!title || !date) {
      alert('수업 제목과 수업 일자를 입력해주세요.');
      return;
    }

    // Collect materials
    const materials = [];
    document.querySelectorAll('#material-builder-list .material-row').forEach(row => {
      const kind = row.querySelector('.mat-kind').value;
      const matTitle = row.querySelector('.mat-title').value.trim();
      let matUrl = '';
      let matSize = '';
      
      if (kind === 'FILE') {
        const fileInput = row.querySelector('.mat-file');
        if (fileInput && fileInput.files && fileInput.files.length > 0) {
          const file = fileInput.files[0];
          matUrl = file.name; // Use filename for mockup display
          matSize = (file.size / 1024 / 1024).toFixed(1) + ' MB';
        } else {
          matUrl = '#'; // Fallback
        }
      } else {
        matUrl = row.querySelector('.mat-url').value.trim() || '#';
      }

      if (matTitle) {
        materials.push({ kind, title: matTitle, url: matUrl, size: matSize });
      }
    });

    if (editId) {
      // Update
      const idx = lessons.findIndex(l => l.id === parseInt(editId));
      if (idx !== -1) {
        lessons[idx] = {
          ...lessons[idx],
          order,
          date,
          title,
          blogUrl,
          videoUrl,
          materials
        };
      }
      showToast(`${order}회차 수업 정보가 수정되었습니다. (학생 화면 즉시 반영)`);
    } else {
      // Create
      const newLesson = {
        id: Date.now(),
        order,
        date,
        title,
        blogUrl,
        videoUrl,
        materials
      };
      lessons.push(newLesson);
      showToast('새 차시가 등록되었습니다. (학생 화면 즉시 반영)');
    }

    lessons.sort((a, b) => a.order - b.order);
    saveToStorage();
    closeModal('lesson-modal');
    renderTable();
  }

  // Quick Video Modal
  function openQuickVideoModal(id) {
    const lesson = lessons.find(l => l.id === id);
    if (!lesson) return;

    document.getElementById('quick-lesson-id').value = lesson.id;
    document.getElementById('quick-lesson-target').textContent = `[${lesson.order}회차] ${lesson.title}`;
    document.getElementById('quick-video-input').value = lesson.videoUrl || '';
    updateQuickPreview();
    openModal('quick-video-modal');
  }

  function updateQuickPreview() {
    const url = document.getElementById('quick-video-input').value.trim();
    const box = document.getElementById('quick-video-preview');
    const thumbImg = document.getElementById('quick-thumb-preview');
    const idDisplay = document.getElementById('quick-video-id');

    const vId = getYouTubeId(url);

    if (vId) {
      box.style.display = 'flex';
      thumbImg.src = `https://img.youtube.com/vi/${vId}/mqdefault.jpg`;
      idDisplay.textContent = `Video ID: ${vId}`;
    } else {
      box.style.display = 'none';
      thumbImg.src = '';
    }
  }

  function saveQuickVideo() {
    const id = parseInt(document.getElementById('quick-lesson-id').value);
    const videoUrl = document.getElementById('quick-video-input').value.trim();

    const idx = lessons.findIndex(l => l.id === id);
    if (idx !== -1) {
      lessons[idx].videoUrl = videoUrl || null;
      saveToStorage();
      showToast(`${lessons[idx].order}회차 유튜브 영상이 저장되었습니다. (학생 화면 즉시 반영)`);
    }

    closeModal('quick-video-modal');
    renderTable();
  }

  // Delete & Undo
  function deleteLesson(id) {
    const idx = lessons.findIndex(l => l.id === id);
    if (idx === -1) return;

    deletedLessonBackup = { index: idx, data: lessons[idx] };
    const order = lessons[idx].order;
    lessons.splice(idx, 1);
    saveToStorage();
    renderTable();

    showToast(`${order}회차가 삭제되었습니다.`, true);
  }

  function undoDelete() {
    if (deletedLessonBackup) {
      lessons.splice(deletedLessonBackup.index, 0, deletedLessonBackup.data);
      lessons.sort((a, b) => a.order - b.order);
      deletedLessonBackup = null;
      saveToStorage();
      renderTable();
      showToast('삭제가 취소되었습니다.');
    }
  }

  // Common Modal Controls
  function openModal(id) {
    document.getElementById(id).classList.add('show');
    document.body.classList.add('modal-open');
  }

  function closeModal(id) {
    document.getElementById(id).classList.remove('show');
    document.body.classList.remove('modal-open');
  }

  function handleBackdropClick(e, id) {
    if (e.target.id === id) {
      closeModal(id);
    }
  }

  // Toast
  let toastTimer = null;
  function showToast(msg, canUndo = false) {
    const toast = document.getElementById('toast');
    document.getElementById('toast-text').textContent = msg;
    const undoBtn = document.getElementById('toast-undo');
    undoBtn.style.display = canUndo ? 'inline-block' : 'none';

    toast.classList.add('show');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => {
      toast.classList.remove('show');
    }, 3200);
  }

  // Real-time synchronization
  

  // Init
  loadLessons();

