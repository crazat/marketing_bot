// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// 바이럴 헌터 웹앱 (JavaScript) - 리스트 선택 방식
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

// 전역 상태
const state = {
    currentView: 'home',
    selectedCategory: null,
    allTargets: [],          // 모든 타겟
    filteredTargets: [],     // 필터링된 타겟
    selectedTargetId: null,  // 현재 선택된 타겟 ID
    checkedTargetIds: new Set(), // 체크된 타겟 ID들
    generatedComments: {},   // targetId -> comment 매핑
    completionStats: {
        approved: 0,
        skipped: 0,
        deleted: 0
    }
};

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// 유틸리티 함수
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

function showScreen(screenName) {
    document.querySelectorAll('.screen').forEach(screen => {
        screen.classList.remove('active');
    });
    document.getElementById(`${screenName}-screen`).classList.add('active');
    state.currentView = screenName;
}

function showToast(message) {
    const toast = document.getElementById('toast');
    toast.textContent = message;
    toast.classList.remove('hidden');
    setTimeout(() => toast.classList.add('hidden'), 3000);
}

function getPriorityClass(priority) {
    if (priority >= 80) return 'priority-high';
    if (priority >= 50) return 'priority-medium';
    return 'priority-low';
}

function getPriorityIcon(priority) {
    if (priority >= 80) return '🔴';
    if (priority >= 50) return '🟡';
    return '🟢';
}

function getStarRating(score) {
    if (score >= 90) return '⭐⭐⭐⭐⭐';
    if (score >= 70) return '⭐⭐⭐⭐';
    return '⭐⭐⭐';
}

function getPlatformName(platform) {
    const platforms = {
        'cafe': '☕ 네이버 카페',
        'blog': '📝 블로그',
        'kin': '❓ 지식iN'
    };
    return platforms[platform] || '📌 기타';
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// 홈 화면
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async function loadHome() {
    try {
        const statsResponse = await fetch('/api/stats');
        const stats = await statsResponse.json();

        document.getElementById('stat-total').textContent = stats.total || 0;
        document.getElementById('stat-pending').textContent = stats.by_status?.pending || 0;
        document.getElementById('stat-posted').textContent = stats.by_status?.posted || 0;
        document.getElementById('stat-skipped').textContent = stats.by_status?.skipped || 0;

        const categoriesResponse = await fetch('/api/categories');
        const categories = await categoriesResponse.json();

        const categoriesList = document.getElementById('categories-list');
        categoriesList.innerHTML = '';

        if (categories.length === 0) {
            categoriesList.innerHTML = `
                <div class="info-box">
                    <p>🔍 작업 가능한 타겟이 없습니다. 먼저 스캔을 실행하세요.</p>
                    <code style="display: block; margin-top: 10px; background: #2D2D3D; padding: 10px; border-radius: 5px;">
                        python viral_hunter.py --scan
                    </code>
                </div>
            `;
            return;
        }

        categories.forEach(([category, stats]) => {
            const priority = stats.priority;
            const priorityClass = getPriorityClass(priority);
            const priorityIcon = getPriorityIcon(priority);

            const card = document.createElement('div');
            card.className = `category-card ${priorityClass}`;
            card.innerHTML = `
                <div class="category-info">
                    <h3>${priorityIcon} ${category}</h3>
                    <div class="category-stats">
                        <p><strong>📦 대기 타겟:</strong> ${stats.count}개</p>
                        <p><strong>⭐ 최고 점수:</strong> ${stats.max_score.toFixed(0)}점</p>
                        <p><strong>📊 평균 점수:</strong> ${stats.avg_score.toFixed(1)}점</p>
                    </div>
                </div>
                <div class="category-action">
                    <button class="btn btn-primary btn-large" onclick="startWork('${category}')">
                        → 작업 시작
                    </button>
                </div>
            `;
            categoriesList.appendChild(card);
        });

    } catch (error) {
        console.error('홈 로딩 실패:', error);
        showToast('❌ 데이터 로딩 실패');
    }
}

function startWork(category) {
    state.selectedCategory = category;
    state.selectedTargetId = null;
    state.checkedTargetIds.clear();
    state.generatedComments = {};
    state.completionStats = { approved: 0, skipped: 0, deleted: 0 };
    loadWorkScreen();
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// 작업 화면
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async function loadWorkScreen() {
    showScreen('work');
    document.getElementById('work-category-title').textContent = `${state.selectedCategory} 카테고리 작업`;

    try {
        const response = await fetch(`/api/targets/${encodeURIComponent(state.selectedCategory)}`);
        state.allTargets = await response.json();
        state.filteredTargets = [...state.allTargets];

        if (state.allTargets.length === 0) {
            showCompletionScreen();
            return;
        }

        updateWorkStats();
        renderTargetList();
        updateBatchButtons();

    } catch (error) {
        console.error('타겟 로딩 실패:', error);
        showToast('❌ 타겟 로딩 실패');
    }
}

function updateWorkStats() {
    document.getElementById('work-total').textContent = state.filteredTargets.length;
    document.getElementById('work-selected').textContent = state.checkedTargetIds.size;

    const pendingCount = state.filteredTargets.filter(t => !['posted', 'skipped', 'deleted'].includes(t.comment_status)).length;
    document.getElementById('work-pending').textContent = pendingCount;
}

function renderTargetList() {
    const listContainer = document.getElementById('target-list');
    listContainer.innerHTML = '';

    if (state.filteredTargets.length === 0) {
        listContainer.innerHTML = '<p style="text-align: center; color: #888; padding: 20px;">검색 결과가 없습니다.</p>';
        return;
    }

    state.filteredTargets.forEach(target => {
        const item = document.createElement('div');
        item.className = 'target-list-item';
        if (target.id === state.selectedTargetId) item.classList.add('selected');
        if (state.checkedTargetIds.has(target.id)) item.classList.add('checked');

        const score = target.priority_score;
        const scoreColor = score >= 90 ? '#FF4444' : score >= 70 ? '#FFD700' : '#4488FF';

        item.innerHTML = `
            <input type="checkbox" onclick="toggleCheck('${target.id}', event)" ${state.checkedTargetIds.has(target.id) ? 'checked' : ''}>
            <div class="target-list-item-content" onclick="selectTarget('${target.id}')">
                <div class="target-list-item-title">${target.title}</div>
                <div class="target-list-item-meta">
                    <span>${getPlatformName(target.platform)}</span>
                    <span style="color: ${scoreColor}; font-weight: bold;">${score.toFixed(0)}점</span>
                </div>
            </div>
        `;

        listContainer.appendChild(item);
    });
}

function toggleCheck(targetId, event) {
    event.stopPropagation();

    if (state.checkedTargetIds.has(targetId)) {
        state.checkedTargetIds.delete(targetId);
    } else {
        state.checkedTargetIds.add(targetId);
    }

    updateWorkStats();
    renderTargetList();
    updateBatchButtons();
}

function selectTarget(targetId) {
    state.selectedTargetId = targetId;
    renderTargetList();
    showTargetDetail();
}

function showTargetDetail() {
    const target = state.allTargets.find(t => t.id === state.selectedTargetId);
    if (!target) return;

    document.getElementById('no-selection').style.display = 'none';
    document.getElementById('target-detail').classList.remove('hidden');

    // 타겟 정보 표시
    document.getElementById('target-title').textContent = target.title;

    const score = target.priority_score;
    const stars = getStarRating(score);
    const scoreColor = score >= 90 ? '#FF4444' : score >= 70 ? '#FFD700' : '#4488FF';
    document.getElementById('target-score').innerHTML = `<span style="color: ${scoreColor}">${stars}<br>(${score.toFixed(0)}점)</span>`;

    document.getElementById('target-platform').textContent = getPlatformName(target.platform);

    const targetUrl = document.getElementById('target-url');
    targetUrl.href = target.url;
    targetUrl.textContent = target.url;

    document.getElementById('target-date').textContent = target.discovered_at || 'N/A';

    const keywords = target.matched_keywords || [];
    document.getElementById('target-keywords').textContent = keywords.slice(0, 10).join(', ') || '없음';

    document.getElementById('content-text').value = target.content_preview || '내용 없음';

    // 댓글 상태
    if (state.generatedComments[target.id]) {
        showGeneratedComment(target.id);
    } else {
        resetCommentState();
    }
}

function resetCommentState() {
    document.getElementById('comment-not-generated').classList.remove('hidden');
    document.getElementById('comment-generated').classList.add('hidden');
    document.getElementById('comment-loading').classList.add('hidden');
    document.getElementById('action-buttons-no-comment').classList.remove('hidden');
    document.getElementById('action-buttons-with-comment').classList.add('hidden');
}

function showGeneratedComment(targetId) {
    document.getElementById('comment-not-generated').classList.add('hidden');
    document.getElementById('comment-generated').classList.remove('hidden');
    document.getElementById('comment-loading').classList.add('hidden');
    document.getElementById('comment-text').value = state.generatedComments[targetId];
    document.getElementById('action-buttons-no-comment').classList.add('hidden');
    document.getElementById('action-buttons-with-comment').classList.remove('hidden');
}

async function generateComment() {
    const target = state.allTargets.find(t => t.id === state.selectedTargetId);
    if (!target) return;

    document.getElementById('comment-not-generated').classList.add('hidden');
    document.getElementById('comment-loading').classList.remove('hidden');

    try {
        const response = await fetch('/api/generate_comment', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                platform: target.platform,
                url: target.url,
                title: target.title,
                content_preview: target.content_preview,
                matched_keywords: target.matched_keywords,
                category: state.selectedCategory,
                priority_score: target.priority_score
            })
        });

        const result = await response.json();

        if (result.success) {
            state.generatedComments[target.id] = result.comment;
            showGeneratedComment(target.id);
            showToast('✅ 댓글 생성 완료!');
        } else {
            throw new Error(result.error);
        }
    } catch (error) {
        console.error('댓글 생성 실패:', error);
        showToast('❌ 댓글 생성 실패');
        resetCommentState();
    }
}

async function approveTarget() {
    const target = state.allTargets.find(t => t.id === state.selectedTargetId);
    const comment = document.getElementById('comment-text').value;

    try {
        const response = await fetch('/api/approve', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ target_id: target.id, comment: comment })
        });

        const result = await response.json();
        if (result.success) {
            showToast('✅ 승인 완료!');
            state.completionStats.approved++;
            removeTargetFromList(target.id);
        } else {
            throw new Error(result.error);
        }
    } catch (error) {
        showToast('❌ 승인 실패');
    }
}

async function skipTarget() {
    const target = state.allTargets.find(t => t.id === state.selectedTargetId);

    try {
        const response = await fetch('/api/skip', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ target_id: target.id })
        });

        const result = await response.json();
        if (result.success) {
            showToast('⏭️ 건너뛰기 완료');
            state.completionStats.skipped++;
            removeTargetFromList(target.id);
        }
    } catch (error) {
        showToast('❌ 건너뛰기 실패');
    }
}

async function deleteTarget() {
    const target = state.allTargets.find(t => t.id === state.selectedTargetId);

    try {
        const response = await fetch('/api/delete', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ target_id: target.id })
        });

        const result = await response.json();
        if (result.success) {
            showToast('🗑️ 삭제 완료');
            state.completionStats.deleted++;
            removeTargetFromList(target.id);
        }
    } catch (error) {
        showToast('❌ 삭제 실패');
    }
}

function removeTargetFromList(targetId) {
    state.allTargets = state.allTargets.filter(t => t.id !== targetId);
    state.filteredTargets = state.filteredTargets.filter(t => t.id !== targetId);
    state.checkedTargetIds.delete(targetId);
    delete state.generatedComments[targetId];

    if (state.allTargets.length === 0) {
        showCompletionScreen();
    } else {
        state.selectedTargetId = null;
        document.getElementById('no-selection').style.display = 'flex';
        document.getElementById('target-detail').classList.add('hidden');
        updateWorkStats();
        renderTargetList();
        updateBatchButtons();
    }
}

function regenerateComment() {
    delete state.generatedComments[state.selectedTargetId];
    resetCommentState();
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// 일괄 작업
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

function updateBatchButtons() {
    const hasChecked = state.checkedTargetIds.size > 0;
    document.getElementById('batch-generate-btn').disabled = !hasChecked;
    document.getElementById('batch-approve-btn').disabled = !hasChecked;
    document.getElementById('batch-skip-btn').disabled = !hasChecked;
}

function toggleSelectAll() {
    if (state.checkedTargetIds.size === state.filteredTargets.length) {
        state.checkedTargetIds.clear();
    } else {
        state.filteredTargets.forEach(t => state.checkedTargetIds.add(t.id));
    }
    updateWorkStats();
    renderTargetList();
    updateBatchButtons();
}

async function batchGenerateComments() {
    const targetIds = Array.from(state.checkedTargetIds);
    showToast(`💬 ${targetIds.length}개 댓글 생성 중...`);

    for (const targetId of targetIds) {
        const target = state.allTargets.find(t => t.id === targetId);
        if (!target || state.generatedComments[target.id]) continue;

        try {
            const response = await fetch('/api/generate_comment', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    platform: target.platform,
                    url: target.url,
                    title: target.title,
                    content_preview: target.content_preview,
                    matched_keywords: target.matched_keywords,
                    category: state.selectedCategory,
                    priority_score: target.priority_score
                })
            });

            const result = await response.json();
            if (result.success) {
                state.generatedComments[target.id] = result.comment;
            }
        } catch (error) {
            console.error('댓글 생성 실패:', target.id);
        }
    }

    showToast(`✅ ${Object.keys(state.generatedComments).length}개 댓글 생성 완료!`);
}

async function batchApprove() {
    const targetIds = Array.from(state.checkedTargetIds);
    let successCount = 0;

    for (const targetId of targetIds) {
        const target = state.allTargets.find(t => t.id === targetId);
        const comment = state.generatedComments[targetId] || '';

        try {
            const response = await fetch('/api/approve', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ target_id: target.id, comment: comment })
            });

            if ((await response.json()).success) {
                successCount++;
                state.completionStats.approved++;
            }
        } catch (error) {
            console.error('승인 실패:', targetId);
        }
    }

    // 처리된 타겟 제거
    targetIds.forEach(id => {
        state.allTargets = state.allTargets.filter(t => t.id !== id);
        state.filteredTargets = state.filteredTargets.filter(t => t.id !== id);
    });

    state.checkedTargetIds.clear();
    state.selectedTargetId = null;

    if (state.allTargets.length === 0) {
        showCompletionScreen();
    } else {
        document.getElementById('no-selection').style.display = 'flex';
        document.getElementById('target-detail').classList.add('hidden');
        updateWorkStats();
        renderTargetList();
        updateBatchButtons();
        showToast(`✅ ${successCount}개 승인 완료!`);
    }
}

async function batchSkip() {
    const targetIds = Array.from(state.checkedTargetIds);
    let successCount = 0;

    for (const targetId of targetIds) {
        try {
            const response = await fetch('/api/skip', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ target_id: targetId })
            });

            if ((await response.json()).success) {
                successCount++;
                state.completionStats.skipped++;
            }
        } catch (error) {
            console.error('건너뛰기 실패:', targetId);
        }
    }

    targetIds.forEach(id => {
        state.allTargets = state.allTargets.filter(t => t.id !== id);
        state.filteredTargets = state.filteredTargets.filter(t => t.id !== id);
    });

    state.checkedTargetIds.clear();
    state.selectedTargetId = null;

    if (state.allTargets.length === 0) {
        showCompletionScreen();
    } else {
        document.getElementById('no-selection').style.display = 'flex';
        document.getElementById('target-detail').classList.add('hidden');
        updateWorkStats();
        renderTargetList();
        updateBatchButtons();
        showToast(`⏭️ ${successCount}개 건너뛰기 완료!`);
    }
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// 검색
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

function searchTargets(query) {
    if (!query.trim()) {
        state.filteredTargets = [...state.allTargets];
    } else {
        const lowerQuery = query.toLowerCase();
        state.filteredTargets = state.allTargets.filter(t =>
            t.title.toLowerCase().includes(lowerQuery) ||
            (t.matched_keywords || []).some(k => k.toLowerCase().includes(lowerQuery))
        );
    }
    updateWorkStats();
    renderTargetList();
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// 완료 화면
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

function showCompletionScreen() {
    showScreen('completion');

    document.getElementById('completion-message').textContent =
        `'${state.selectedCategory}' 카테고리의 모든 작업을 완료했습니다!`;

    const stats = state.completionStats;
    const total = stats.approved + stats.skipped + stats.deleted;

    document.getElementById('completion-total').textContent = total;
    document.getElementById('completion-approved').textContent = stats.approved;
    document.getElementById('completion-skipped').textContent = stats.skipped;
    document.getElementById('completion-deleted').textContent = stats.deleted;

    const approvalRate = total > 0 ? (stats.approved / total) * 100 : 0;
    document.getElementById('approval-rate-fill').style.width = `${approvalRate}%`;
    document.getElementById('approval-rate-text').textContent = `${approvalRate.toFixed(1)}%`;
}

function goHome() {
    state.selectedCategory = null;
    state.allTargets = [];
    state.filteredTargets = [];
    state.selectedTargetId = null;
    state.checkedTargetIds.clear();
    state.generatedComments = {};
    state.completionStats = { approved: 0, skipped: 0, deleted: 0 };

    showScreen('home');
    loadHome();
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// 이벤트 리스너
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

document.addEventListener('DOMContentLoaded', () => {
    loadHome();

    document.getElementById('back-btn').addEventListener('click', goHome);
    document.getElementById('completion-home-btn').addEventListener('click', goHome);

    document.getElementById('toggle-content-btn').addEventListener('click', () => {
        const preview = document.getElementById('target-content-preview');
        const btn = document.getElementById('toggle-content-btn');
        if (preview.classList.contains('hidden')) {
            preview.classList.remove('hidden');
            btn.textContent = '📄 내용 미리보기 접기';
        } else {
            preview.classList.add('hidden');
            btn.textContent = '📄 내용 미리보기 펼치기';
        }
    });

    document.getElementById('generate-btn').addEventListener('click', generateComment);
    document.getElementById('regenerate-btn').addEventListener('click', regenerateComment);

    document.getElementById('approve-btn').addEventListener('click', approveTarget);
    document.getElementById('skip-btn-with-comment').addEventListener('click', skipTarget);
    document.getElementById('delete-btn-with-comment').addEventListener('click', deleteTarget);
    document.getElementById('skip-btn-no-comment').addEventListener('click', skipTarget);
    document.getElementById('delete-btn-no-comment').addEventListener('click', deleteTarget);

    // 일괄 작업
    document.getElementById('select-all-btn').addEventListener('click', toggleSelectAll);
    document.getElementById('batch-generate-btn').addEventListener('click', batchGenerateComments);
    document.getElementById('batch-approve-btn').addEventListener('click', batchApprove);
    document.getElementById('batch-skip-btn').addEventListener('click', batchSkip);

    // 검색
    document.getElementById('search-input').addEventListener('input', (e) => {
        searchTargets(e.target.value);
    });
});
