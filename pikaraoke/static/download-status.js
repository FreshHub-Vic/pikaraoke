/**
 * Shared download status panel: active progress, pending downloads, and errors.
 *
 * Rendered on any page that includes _download_status.html. Download failures
 * would otherwise only appear as a transient toast, leaving no trace of why a
 * song never showed up.
 */
(function () {
    'use strict';

    const config = {
        statusUrl: '/queue/downloads',
        dismissUrlPrefix: '/queue/downloads/errors/',
        sectionSelector: '#downloads-section',
        containerSelector: '#downloads-container',
        pollIntervalMs: 500
    };

    // Keeps long titles and error output to a single line; the full text is
    // available via the title attribute
    const TRUNCATE = 'overflow: hidden; text-overflow: ellipsis; white-space: nowrap;';

    let pollTimer = null;
    let isInitialized = false;

    /**
     * Look up a translated string, falling back to English.
     * @param {string} key - Key in window.i18n
     * @param {string} fallback
     * @returns {string}
     */
    function t(key, fallback) {
        return (window.i18n && window.i18n[key]) || fallback;
    }

    /**
     * Escape text for safe interpolation into HTML, including attribute values.
     * yt-dlp stderr and YouTube titles are untrusted and routinely contain
     * angle brackets and quotes: its output quotes format strings like "-f mp4",
     * which would otherwise close a title attribute early.
     * @param {*} value
     * @returns {string}
     */
    function escapeHtml(value) {
        return String(value === null || value === undefined ? '' : value)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    /**
     * @param {Object} d - Active download status
     * @returns {string} HTML
     */
    function renderActive(d) {
        let progressClass = 'is-info';
        if (d.status === 'complete') progressClass = 'is-success';
        if (d.status === 'error') progressClass = 'is-danger';

        return `
            <div class="box mb-4 has-background-dark">
                <h4 class="title is-5 mb-2">${escapeHtml(d.title)}</h4>
                <!-- inline style to ensure background visibility if theme overrides it -->
                <progress class="progress ${progressClass}" value="${escapeHtml(d.progress)}" max="100" style="background-color: #dbdbdb;">${escapeHtml(d.progress)}%</progress>
                <div class="level is-mobile is-size-7 mt-1">
                    <div class="level-left">
                        <span class="level-item text-muted"><b>Status:</b>&nbsp;${escapeHtml(d.status)}</span>
                    </div>
                    <div class="level-right">
                        <span class="level-item"><b>Speed:</b>&nbsp;${escapeHtml(d.speed)}&nbsp;&nbsp;&nbsp;<b>ETA:</b>&nbsp;${escapeHtml(d.eta)}</span>
                    </div>
                </div>
            </div>
        `;
    }

    /**
     * @param {Array<Object>} pending
     * @returns {string} HTML
     */
    function renderPending(pending) {
        let html = `<div class="content"><h5 class="title is-6 mb-2">${escapeHtml(t('downloadsPending', 'Pending downloads'))}</h5>`;
        pending.forEach(function (d) {
            html += `
                <div class="box mb-2 p-3 has-background-dark is-flex is-align-items-center">
                    <span class="has-text-grey">${escapeHtml(d.display_title || d.video_url)}</span>
                    <span class="tag is-light is-rounded ml-auto">${escapeHtml(t('downloadsQueued', 'Queued'))}</span>
                </div>
            `;
        });
        return html + `</div>`;
    }

    /**
     * Reduce yt-dlp output to the line that states the cause.
     * The raw output is dozens of progress and warning lines; showing all of it
     * buries the reason the download failed. Full text stays in the tooltip.
     * @param {string} output
     * @returns {string}
     */
    function summarizeError(output) {
        const lines = String(output || '')
            .split('\n')
            .map(function (line) { return line.trim(); })
            .filter(Boolean);
        const errorLines = lines.filter(function (line) { return line.indexOf('ERROR:') === 0; });
        const summary = errorLines.length
            ? errorLines[errorLines.length - 1].replace(/^ERROR:\s*/, '')
            : lines[lines.length - 1];
        return summary || 'Unknown error';
    }

    /**
     * @param {Array<Object>} errors
     * @returns {string} HTML
     */
    function renderErrors(errors) {
        let html = `<div class="content"><h5 class="title is-6 mb-2 has-text-danger">${escapeHtml(t('downloadsErrors', 'Download Errors'))}</h5>`;
        errors.forEach(function (d) {
            const label = escapeHtml(d.title || d.url);
            const summary = escapeHtml(summarizeError(d.error));
            const fullError = escapeHtml(d.error);
            html += `
                <div class="box mb-2 p-3 has-background-white-ter is-flex is-align-items-center" style="border-left: 4px solid #f14668;">
                    <span class="icon has-text-danger mr-2"><i class="icon-cancel"></i></span>
                    <div class="is-flex-grow-1" style="min-width: 0;">
                        <p class="has-text-grey mb-0" style="${TRUNCATE}" title="${label}">${label}</p>
                        <p class="help is-danger mb-0" style="${TRUNCATE}" title="${fullError}">${summary}</p>
                    </div>
                    <span class="tag is-danger is-light is-rounded ml-2">${escapeHtml(t('downloadsFailed', 'Failed'))}</span>
                    <button class="delete ml-2 download-error-dismiss" data-error-id="${escapeHtml(d.id)}" title="${escapeHtml(t('downloadsDismiss', 'Dismiss'))}"></button>
                </div>
            `;
        });
        return html + `</div>`;
    }

    /**
     * Fetch the current download status and render the panel.
     * Continues polling only while something is active or pending.
     */
    function refresh() {
        if (pollTimer) {
            clearTimeout(pollTimer);
            pollTimer = null;
        }

        // Stop if the panel is not on the current page (e.g. after SPA navigation)
        if ($(config.sectionSelector).length === 0) {
            return;
        }

        $.get(config.statusUrl, function (data) {
            const status = JSON.parse(data);
            let html = '';

            if (status.active) {
                html += renderActive(status.active);
            }
            if (status.pending && status.pending.length > 0) {
                html += renderPending(status.pending);
            }
            if (status.errors && status.errors.length > 0) {
                html += renderErrors(status.errors);
            }

            if (html) {
                $(config.containerSelector).html(html);
                $(config.sectionSelector).fadeIn();
            } else {
                // Clear only once hidden, so the panel does not empty mid-fade
                $(config.sectionSelector).fadeOut(function () {
                    $(config.containerSelector).empty();
                });
            }

            // Errors are static once recorded, so they don't need polling
            const shouldPoll = status.active || (status.pending && status.pending.length > 0);
            if (shouldPoll && $(config.sectionSelector).length > 0) {
                pollTimer = setTimeout(refresh, config.pollIntervalMs);
            }
        });
    }

    /**
     * Dismiss a recorded download error.
     * @param {string} errorId
     */
    function dismissError(errorId) {
        $.ajax({
            url: config.dismissUrlPrefix + encodeURIComponent(errorId),
            type: 'DELETE',
            success: function () {
                // Refresh immediately since polling may be stopped
                refresh();
            }
        });
    }

    /**
     * Bind delegated handlers and socket listeners. Safe to call repeatedly.
     */
    function init() {
        if (!isInitialized) {
            $(document).on('click', '.download-error-dismiss', function (e) {
                e.preventDefault();
                dismissError($(this).data('error-id'));
            });
            isInitialized = true;
        }

        if (typeof window.socket === 'undefined' && typeof io === 'function') {
            window.socket = io();
        }

        if (window.socket) {
            window.socket.off('download_started');
            window.socket.on('download_started', function () {
                if (!pollTimer) {
                    refresh();
                }
            });

            window.socket.off('download_stopped');
            window.socket.on('download_stopped', function () {
                // One final fetch to show completion or errors, then stop
                refresh();
            });
        }

        refresh();
    }

    window.DownloadStatus = { init: init, refresh: refresh };

    $(document).ready(init);
})();
