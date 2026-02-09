/* ============================================================
   SYSC4907 First-Year Schedule Manager — Main JavaScript
   ============================================================ */

(function () {
    'use strict';

    /* ---------------------------------------------------------
       DOM READY
       --------------------------------------------------------- */
    document.addEventListener('DOMContentLoaded', function () {
        initSidebar();
        initBlockToggles();
        initTermTabs();
        initTimetables();
        initAutoCloseAlerts();
    });


    /* =========================================================
       SIDEBAR
       ========================================================= */
    function initSidebar() {
        var sidebar = document.getElementById('sidebar');
        var openBtn = document.getElementById('sidebar-open');
        var closeBtn = document.getElementById('sidebar-close');

        if (!sidebar) return;

        // Create backdrop element
        var backdrop = document.createElement('div');
        backdrop.className = 'sidebar-backdrop';
        document.body.appendChild(backdrop);

        function openSidebar() {
            sidebar.classList.add('open');
            backdrop.classList.add('visible');
            document.body.style.overflow = 'hidden';
        }

        function closeSidebar() {
            sidebar.classList.remove('open');
            backdrop.classList.remove('visible');
            document.body.style.overflow = '';
        }

        if (openBtn) {
            openBtn.addEventListener('click', openSidebar);
        }
        if (closeBtn) {
            closeBtn.addEventListener('click', closeSidebar);
        }
        backdrop.addEventListener('click', closeSidebar);

        // Close sidebar on Escape key
        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape' && sidebar.classList.contains('open')) {
                closeSidebar();
            }
        });
    }


    /* =========================================================
       BLOCK CARD TOGGLES (expand / collapse)
       ========================================================= */
    function initBlockToggles() {
        var headers = document.querySelectorAll('.block-card-header[data-toggle]');

        headers.forEach(function (header) {
            var targetId = header.getAttribute('data-toggle');
            var content = document.getElementById(targetId);
            if (!content) return;

            // Start collapsed
            var isOpen = header.getAttribute('aria-expanded') === 'true';
            if (isOpen) {
                content.classList.add('open');
            }

            header.addEventListener('click', function () {
                var expanded = content.classList.toggle('open');
                header.setAttribute('aria-expanded', expanded ? 'true' : 'false');
            });
        });
    }


    /* =========================================================
       TERM TABS
       ========================================================= */
    function initTermTabs() {
        var tabGroups = document.querySelectorAll('.term-tabs');

        tabGroups.forEach(function (group) {
            var tabs = group.querySelectorAll('.term-tab');

            tabs.forEach(function (tab) {
                tab.addEventListener('click', function () {
                    var targetTerm = tab.getAttribute('data-term');

                    // Deactivate siblings
                    tabs.forEach(function (t) { t.classList.remove('active'); });
                    tab.classList.add('active');

                    // Show/hide block cards
                    var container = group.parentElement;
                    if (!container) return;

                    var blocks = container.querySelectorAll('.block-card[data-term]');
                    blocks.forEach(function (block) {
                        if (targetTerm === 'all' || block.getAttribute('data-term') === targetTerm) {
                            block.style.display = '';
                        } else {
                            block.style.display = 'none';
                        }
                    });
                });
            });
        });
    }


    /* =========================================================
       TIMETABLE RENDERING
       ========================================================= */

    // Color palette — maps course codes to consistent colors
    var courseColorMap = {};
    var courseColorIndex = 0;
    var TOTAL_COLORS = 12;

    function getCourseColorClass(courseCode) {
        if (!courseColorMap[courseCode]) {
            courseColorIndex++;
            courseColorMap[courseCode] = ((courseColorIndex - 1) % TOTAL_COLORS) + 1;
        }
        return 'tt-course-' + courseColorMap[courseCode];
    }

    /**
     * Initialise all timetable containers on the page.
     * Each container should have:
     *   data-timetable="true"
     *   A <script type="application/json" class="tt-data"> child with the course JSON.
     */
    function initTimetables() {
        var containers = document.querySelectorAll('[data-timetable]');

        containers.forEach(function (container) {
            var dataEl = container.querySelector('.tt-data');
            if (!dataEl) return;

            try {
                var courses = JSON.parse(dataEl.textContent);
                renderTimetable(container, courses);
            } catch (e) {
                console.error('Error parsing timetable data:', e);
                container.innerHTML = '<p class="text-muted text-sm" style="padding:1rem;">Could not render timetable.</p>';
            }
        });
    }

    /**
     * Renders an HTML timetable grid inside the given container.
     * @param {HTMLElement} container
     * @param {Array} courses  — [{code, section, type, days, start_time, end_time}, ...]
     */
    function renderTimetable(container, courses) {
        if (!courses || courses.length === 0) {
            container.innerHTML = '<p class="text-muted text-sm" style="padding:1rem;">No courses scheduled.</p>';
            return;
        }

        var START_HOUR = 8;
        var END_HOUR = 22;
        var SLOT_MINUTES = 30;
        var TOTAL_SLOTS = ((END_HOUR - START_HOUR) * 60) / SLOT_MINUTES;
        var DAY_NAMES = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri'];
        var DAY_MAP = { 'M': 0, 'T': 1, 'W': 2, 'R': 3, 'F': 4 };

        // Parse courses into slot objects
        var events = [];
        courses.forEach(function (c) {
            if (!c.days || !c.start_time || !c.end_time) return;

            var startMin = parseTimeToMinutes(c.start_time);
            var endMin = parseTimeToMinutes(c.end_time);

            var days = c.days.split('').filter(function (d) { return d in DAY_MAP; });

            days.forEach(function (d) {
                events.push({
                    code: c.code,
                    section: c.section,
                    type: c.type,
                    dayIndex: DAY_MAP[d],
                    startSlot: (startMin - START_HOUR * 60) / SLOT_MINUTES,
                    endSlot: (endMin - START_HOUR * 60) / SLOT_MINUTES,
                    startMin: startMin,
                    endMin: endMin
                });
            });
        });

        // Build the table
        var table = document.createElement('table');
        table.className = 'timetable';

        // Header row
        var thead = document.createElement('thead');
        var headerRow = document.createElement('tr');
        var timeHeader = document.createElement('th');
        timeHeader.textContent = 'Time';
        headerRow.appendChild(timeHeader);

        DAY_NAMES.forEach(function (name) {
            var th = document.createElement('th');
            th.textContent = name;
            headerRow.appendChild(th);
        });
        thead.appendChild(headerRow);
        table.appendChild(thead);

        // Body
        var tbody = document.createElement('tbody');
        for (var slot = 0; slot < TOTAL_SLOTS; slot++) {
            var tr = document.createElement('tr');

            // Time label
            var timeTd = document.createElement('td');
            var totalMin = START_HOUR * 60 + slot * SLOT_MINUTES;
            var mins = totalMin % 60;
            if (mins === 0) {
                timeTd.textContent = formatMinutesToTime(totalMin);
            }
            tr.appendChild(timeTd);

            // Day columns
            for (var day = 0; day < 5; day++) {
                var td = document.createElement('td');
                td.setAttribute('data-slot', slot);
                td.setAttribute('data-day', day);
                tr.appendChild(td);
            }

            tbody.appendChild(tr);
        }
        table.appendChild(tbody);

        // Place events as absolutely positioned elements
        var wrapper = document.createElement('div');
        wrapper.className = 'timetable-wrapper';
        wrapper.appendChild(table);
        container.innerHTML = '';
        container.appendChild(wrapper);

        // After rendering, position course blocks
        requestAnimationFrame(function () {
            positionEvents(table, events, TOTAL_SLOTS);
        });
    }

    function positionEvents(table, events, totalSlots) {
        var tbody = table.querySelector('tbody');
        if (!tbody) return;

        var rows = tbody.querySelectorAll('tr');
        if (rows.length === 0) return;

        events.forEach(function (evt) {
            var startSlot = Math.max(0, Math.floor(evt.startSlot));
            var endSlot = Math.min(totalSlots, Math.ceil(evt.endSlot));

            if (startSlot >= totalSlots || endSlot <= 0) return;

            // Find the target cell for the starting slot
            var startRow = rows[startSlot];
            if (!startRow) return;

            // Day column is offset by 1 (first column = time)
            var cell = startRow.children[evt.dayIndex + 1];
            if (!cell) return;

            var slotHeight = cell.offsetHeight || 48;
            var topOffset = (evt.startSlot - startSlot) * slotHeight;
            var height = (evt.endSlot - evt.startSlot) * slotHeight;

            var div = document.createElement('div');
            div.className = 'tt-course ' + getCourseColorClass(evt.code);
            div.style.top = topOffset + 'px';
            div.style.height = Math.max(height - 2, 18) + 'px';

            var startTimeStr = formatMinutesToTime(evt.startMin);
            var endTimeStr = formatMinutesToTime(evt.endMin);

            div.innerHTML =
                '<span class="tt-course-code">' + escapeHtml(evt.code) + '</span>' +
                '<span class="tt-course-section">' + escapeHtml(evt.section) + ' &middot; ' + escapeHtml(evt.type) + '</span>';

            div.setAttribute('data-tooltip', evt.code + ' ' + evt.section + ' (' + evt.type + ') ' + startTimeStr + '-' + endTimeStr);

            cell.style.position = 'relative';
            cell.appendChild(div);
        });
    }


    /* =========================================================
       AJAX HELPERS
       ========================================================= */

    /**
     * Show loading overlay with a custom message.
     */
    window.showLoading = function (message) {
        var overlay = document.getElementById('loading-overlay');
        var msgEl = document.getElementById('loading-message');
        if (overlay) {
            overlay.style.display = 'flex';
        }
        if (msgEl && message) {
            msgEl.textContent = message;
        }
    };

    /**
     * Hide loading overlay.
     */
    window.hideLoading = function () {
        var overlay = document.getElementById('loading-overlay');
        if (overlay) {
            overlay.style.display = 'none';
        }
    };

    /**
     * Show a toast notification.
     * @param {string} message
     * @param {'success'|'error'|'info'} type
     * @param {number} duration — ms before auto-dismiss (default 4000)
     */
    window.showToast = function (message, type, duration) {
        type = type || 'info';
        duration = duration || 4000;

        var container = document.getElementById('toast-container');
        if (!container) return;

        var toast = document.createElement('div');
        toast.className = 'toast toast-' + type;

        var icon = '';
        if (type === 'success') {
            icon = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path><polyline points="22 4 12 14.01 9 11.01"></polyline></svg>';
        } else if (type === 'error') {
            icon = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="15" y1="9" x2="9" y2="15"></line><line x1="9" y1="9" x2="15" y2="15"></line></svg>';
        } else {
            icon = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="16" x2="12" y2="12"></line><line x1="12" y1="8" x2="12.01" y2="8"></line></svg>';
        }

        toast.innerHTML = icon + '<span>' + escapeHtml(message) + '</span>';
        container.appendChild(toast);

        setTimeout(function () {
            toast.style.opacity = '0';
            toast.style.transform = 'translateX(100%)';
            toast.style.transition = 'all 0.3s ease-in';
            setTimeout(function () {
                if (toast.parentNode) {
                    toast.parentNode.removeChild(toast);
                }
            }, 300);
        }, duration);
    };

    /**
     * Perform an AJAX POST request (with CSRF token from cookies).
     * @param {string} url
     * @param {Object} data
     * @returns {Promise}
     */
    window.ajaxPost = function (url, data) {
        var csrfToken = getCookie('csrftoken');

        return fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken,
                'X-Requested-With': 'XMLHttpRequest'
            },
            body: JSON.stringify(data || {})
        }).then(function (response) {
            if (!response.ok) {
                throw new Error('HTTP error ' + response.status);
            }
            return response.json();
        });
    };


    /* =========================================================
       GENERATE & RANK — page-specific logic
       ========================================================= */

    /**
     * Called from the Generate page button. Triggers schedule generation via AJAX.
     */
    window.triggerGenerate = function (url) {
        showLoading('Generating schedule... This may take a moment.');

        var consoleEl = document.getElementById('console-output');
        if (consoleEl) {
            consoleEl.style.display = 'block';
            consoleEl.textContent = '> Starting schedule generation...\n';
        }

        ajaxPost(url)
            .then(function (data) {
                hideLoading();
                if (data.success) {
                    showToast('Schedule generated successfully!', 'success');
                    if (consoleEl) {
                        consoleEl.textContent += data.log || '> Done.\n';
                    }
                    // Reload after short delay so user sees the toast
                    setTimeout(function () { window.location.reload(); }, 1500);
                } else {
                    showToast(data.error || 'Generation failed.', 'error');
                    if (consoleEl && data.log) {
                        consoleEl.textContent += data.log;
                    }
                }
            })
            .catch(function (err) {
                hideLoading();
                showToast('An error occurred: ' + err.message, 'error');
                if (consoleEl) {
                    consoleEl.textContent += '\n> ERROR: ' + err.message + '\n';
                }
            });
    };

    /**
     * Called from the Generate page button. Triggers ranking via AJAX.
     */
    window.triggerRank = function (url) {
        showLoading('Ranking blocks...');

        ajaxPost(url)
            .then(function (data) {
                hideLoading();
                if (data.success) {
                    showToast('Ranking complete!', 'success');
                    setTimeout(function () { window.location.reload(); }, 1200);
                } else {
                    showToast(data.error || 'Ranking failed.', 'error');
                }
            })
            .catch(function (err) {
                hideLoading();
                showToast('An error occurred: ' + err.message, 'error');
            });
    };


    /* =========================================================
       AUTO-CLOSE ALERTS
       ========================================================= */
    function initAutoCloseAlerts() {
        var alerts = document.querySelectorAll('.alert');
        alerts.forEach(function (alert) {
            setTimeout(function () {
                alert.style.opacity = '0';
                alert.style.transform = 'translateY(-10px)';
                alert.style.transition = 'all 0.3s ease-out';
                setTimeout(function () {
                    if (alert.parentNode) {
                        alert.parentNode.removeChild(alert);
                    }
                }, 300);
            }, 6000);
        });
    }


    /* =========================================================
       UTILITIES
       ========================================================= */

    /**
     * Parse a time value (e.g. "0835" or "1435") into total minutes since midnight.
     */
    function parseTimeToMinutes(timeStr) {
        if (!timeStr) return 0;
        var t = String(timeStr).replace(':', '');
        while (t.length < 4) t = '0' + t;
        var hours = parseInt(t.substring(0, 2), 10);
        var mins = parseInt(t.substring(2, 4), 10);
        return hours * 60 + mins;
    }

    /**
     * Format total minutes since midnight to "HH:MM".
     */
    function formatMinutesToTime(totalMinutes) {
        var h = Math.floor(totalMinutes / 60);
        var m = totalMinutes % 60;
        return (h < 10 ? '0' : '') + h + ':' + (m < 10 ? '0' : '') + m;
    }

    /**
     * Escape HTML entities for safe insertion.
     */
    function escapeHtml(text) {
        if (!text) return '';
        var div = document.createElement('div');
        div.appendChild(document.createTextNode(text));
        return div.innerHTML;
    }

    /**
     * Get a cookie value by name.
     */
    function getCookie(name) {
        var cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            var cookies = document.cookie.split(';');
            for (var i = 0; i < cookies.length; i++) {
                var cookie = cookies[i].trim();
                if (cookie.substring(0, name.length + 1) === (name + '=')) {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        return cookieValue;
    }

})();
