/* ============================================================
   Heartfulness NGO – Main JavaScript
   ============================================================ */

/* ── Chart colour palette ────────────────────────────────── */
const CHART_COLORS = [
  '#2563EB','#10B981','#F59E0B','#EF4444','#8B5CF6',
  '#06B6D4','#EC4899','#84CC16','#F97316','#6366F1'
];

/* ── Theme helpers ───────────────────────────────────────── */
function isDark() {
  return document.documentElement.getAttribute('data-theme') === 'dark';
}

function toggleTheme() {
  const next = isDark() ? 'light' : 'dark';
  document.documentElement.setAttribute('data-theme', next);
  // update icon
  const icon = document.getElementById('themeIcon');
  if (icon) icon.className = next === 'dark' ? 'bi bi-sun-fill' : 'bi bi-moon-fill';
  // persist to server
  fetch('/set-theme?theme=' + next).catch(() => {});
}

/* ── Sidebar toggle ──────────────────────────────────────── */
const MOBILE_BREAKPOINT = 768;

function isMobileViewport() {
  return window.innerWidth <= MOBILE_BREAKPOINT;
}

function toggleSidebar() {
  const sidebar = document.getElementById('sidebar');
  const main    = document.getElementById('mainContent');
  const overlay = document.getElementById('sidebarOverlay');
  if (!sidebar) return;

  if (isMobileViewport()) {
    // On phones (including vertical/portrait orientation) the sidebar is an
    // off-canvas overlay: slide it in/out and dim the rest of the page.
    const opening = !sidebar.classList.contains('active');
    sidebar.classList.toggle('active', opening);
    if (overlay) overlay.classList.toggle('active', opening);
    document.body.classList.toggle('sidebar-open', opening);
  } else {
    // On tablets/desktops the sidebar stays on-canvas and just collapses
    // to an icon rail.
    sidebar.classList.toggle('collapsed');
    if (main) main.classList.toggle('sidebar-collapsed');
  }
}

function closeSidebarMobile() {
  const sidebar = document.getElementById('sidebar');
  const overlay = document.getElementById('sidebarOverlay');
  if (sidebar) sidebar.classList.remove('active');
  if (overlay) overlay.classList.remove('active');
  document.body.classList.remove('sidebar-open');
}

// Keep sidebar state sane when the viewport crosses the mobile breakpoint
// (e.g. rotating a phone, or resizing a browser window).
window.addEventListener('resize', function () {
  const sidebar = document.getElementById('sidebar');
  const main    = document.getElementById('mainContent');
  if (!sidebar) return;
  if (isMobileViewport()) {
    sidebar.classList.remove('collapsed');
    if (main) main.classList.remove('sidebar-collapsed');
  } else {
    closeSidebarMobile();
  }
});

/* ── DOMContentLoaded ────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', function () {

  /* Confirm dialogs */
  document.querySelectorAll('[data-confirm]').forEach(function (el) {
    el.addEventListener('click', function (e) {
      if (!confirm(this.getAttribute('data-confirm'))) {
        e.preventDefault(); e.stopPropagation();
      }
    });
  });

  /* Auto-hide success/info flash messages after 5 s */
  document.querySelectorAll('.alert:not(.alert-danger)').forEach(function (a) {
    setTimeout(function () {
      a.style.transition = 'opacity 0.4s';
      a.style.opacity = '0';
      setTimeout(function () { a.remove(); }, 400);
    }, 5000);
  });

  /* Attendance checkbox → badge sync */
  document.querySelectorAll('.att-checkbox').forEach(function (cb) {
    cb.addEventListener('change', function () {
      updateRowBadge(this);
      updatePresentCount();
    });
  });

  /* Init present-count on attendance page */
  if (document.getElementById('memberList')) updatePresentCount();
});

/* ── Attendance helpers ──────────────────────────────────── */
function selectAllPresent() {
  document.querySelectorAll('.att-checkbox').forEach(function (cb) {
    cb.checked = true; updateRowBadge(cb);
  });
  updatePresentCount();
}
function selectAllAbsent() {
  document.querySelectorAll('.att-checkbox').forEach(function (cb) {
    cb.checked = false; updateRowBadge(cb);
  });
  updatePresentCount();
}
function updateRowBadge(cb) {
  const badge = cb.closest('.attendance-row').querySelector('.badge-present,.badge-absent');
  if (!badge) return;
  badge.className = cb.checked ? 'badge-present' : 'badge-absent';
  badge.textContent = cb.checked ? 'Present' : 'Absent';
}
function updatePresentCount() {
  const all     = document.querySelectorAll('.att-checkbox');
  const present = Array.from(all).filter(c => c.checked).length;
  const el      = document.getElementById('presentCount');
  if (el) el.textContent = present + ' / ' + all.length + ' Present';
}
function filterMembers(q) {
  q = q.toLowerCase();
  document.querySelectorAll('.member-row').forEach(function (row) {
    const name = (row.dataset.name || '').toLowerCase();
    const id   = (row.dataset.id   || '').toLowerCase();
    row.style.display = (name.includes(q) || id.includes(q)) ? '' : 'none';
  });
}
