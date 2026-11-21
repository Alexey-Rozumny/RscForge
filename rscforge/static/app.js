(() => {
  "use strict";

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

  const state = {
    sources: [],
    settings: {},
    readonly: {},
    entries: { items: [], total: 0, limit: 100, offset: 0 },
    filters: { search: "", kind: "", source: "", enabled: "" },
    selected: new Set(),
  };

  function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>"']/g, (character) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;",
    }[character]));
  }

  async function api(path, options = {}) {
    const opts = { ...options };
    if (opts.body && !(opts.body instanceof FormData)) {
      opts.headers = { "Content-Type": "application/json", ...(opts.headers || {}) };
      if (typeof opts.body !== "string") {
        opts.body = JSON.stringify(opts.body);
      }
    }

    const response = await fetch(path, opts);
    if (response.status === 204) {
      return null;
    }

    const contentType = response.headers.get("content-type") || "";
    const data = contentType.includes("application/json")
      ? await response.json()
      : await response.text();

    if (!response.ok) {
      let message = data && data.detail !== undefined ? data.detail : data;
      if (Array.isArray(message)) {
        message = message
          .map((item) => item.msg || JSON.stringify(item))
          .join("; ");
      }
      throw new Error(message || `HTTP ${response.status}`);
    }
    return data;
  }

  let toastTimer;
  function toast(message, kind = "ok") {
    const element = $("#toast");
    element.textContent = message;
    element.className = `toast ${kind}`;
    element.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => {
      element.hidden = true;
    }, 6000);
  }

  function fmtDate(value) {
    if (!value) return "—";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;
    return date.toLocaleString("ru-RU");
  }

  function errorToast(error) {
    toast(error instanceof Error ? error.message : String(error), "err");
  }

  // ---------------------------------------------------------------- tabs

  $$(".tab").forEach((button) => {
    button.addEventListener("click", () => {
      $$(".tab").forEach((item) => item.classList.toggle("active", item === button));
      $$(".panel").forEach((panel) => {
        panel.classList.toggle("active", panel.id === `panel-${button.dataset.tab}`);
      });
      if (button.dataset.tab === "sources") {
        loadSources().catch(errorToast);
      }
      if (button.dataset.tab === "entries") {
        loadEntries().catch(errorToast);
      }
      if (button.dataset.tab === "export") {
        loadPreview().catch(errorToast);
      }
      if (button.dataset.tab === "settings") {
        loadSettings().catch(errorToast);
      }
    });
  });

  // --------------------------------------------------------------- stats

  async function loadStats() {
    const stats = await api("/api/entries/stats");
    $("#stats").innerHTML = `
      <span class="pill"><b>${stats.total}</b> записей</span>
      <span class="pill"><b>${stats.enabled}</b> включено</span>
      <span class="pill"><b>${stats.domains}</b> доменов</span>
      <span class="pill"><b>${stats.ip_entries}</b> ip/cidr</span>
    `;
  }

  // ------------------------------------------------------------- sources

  async function loadSources() {
    state.sources = await api("/api/sources");
    renderSources();
    renderSourceFilter();
    loadStats().catch(() => {});
  }

  function renderSources() {
    const body = $("#sources-body");
    if (!state.sources.length) {
      body.innerHTML = `<tr><td colspan="6" class="empty">Источников пока нет</td></tr>`;
      return;
    }

    body.innerHTML = state.sources.map((source) => {
      const target = source.kind === "url" ? source.url : source.stored_path;
      let status;
      if (source.last_error) {
        status = `<span class="badge err">ошибка</span>`;
      } else if (source.last_status) {
        status = `<span class="badge ok">ok</span>`;
      } else {
        status = `<span class="badge">не обновлялся</span>`;
      }
      const detail = source.last_error || source.last_status || "";
      return `
        <tr>
          <td>
            <div class="strong">${escapeHtml(source.name)}</div>
            <div class="muted small mono">${escapeHtml(target || "")}</div>
          </td>
          <td><span class="badge">${escapeHtml(source.kind)}</span></td>
          <td>${source.enabled_count} / ${source.entry_count}</td>
          <td>${fmtDate(source.last_fetched_at)}</td>
          <td>
            ${status}
            <div class="muted small">${escapeHtml(detail)}</div>
          </td>
          <td class="actions">
            <button class="ghost" type="button" data-action="refresh" data-id="${source.id}">Обновить</button>
            <button class="ghost" type="button" data-action="toggle" data-id="${source.id}">${source.enabled ? "Выкл" : "Вкл"}</button>
            <button class="danger" type="button" data-action="delete" data-id="${source.id}">Удалить</button>
          </td>
        </tr>
      `;
    }).join("");
  }

  function renderSourceFilter() {
    const select = $("#filter-source");
    const current = select.value;
    select.innerHTML = `
      <option value="">Все источники</option>
      <option value="manual">Ручные</option>
      ${state.sources.map((source) => (
        `<option value="${source.id}">${escapeHtml(source.name)}</option>`
      )).join("")}
    `;
    select.value = current;
  }

  $("#sources-body").addEventListener("click", async (event) => {
    const button = event.target.closest("button[data-action]");
    if (!button) return;

    const id = Number(button.dataset.id);
    const source = state.sources.find((item) => item.id === id);
    if (!source) return;

    try {
      if (button.dataset.action === "refresh") {
        button.disabled = true;
        const result = await api(`/api/sources/${id}/refresh`, { method: "POST" });
        if (result.refresh_error) {
          toast(result.refresh_error, "err");
        } else {
          toast(`Источник «${source.name}» обновлён`);
        }
      } else if (button.dataset.action === "toggle") {
        await api(`/api/sources/${id}`, {
          method: "PATCH",
          body: { enabled: !source.enabled },
        });
      } else if (button.dataset.action === "delete") {
        if (!confirm(`Удалить источник «${source.name}» и все его записи?`)) return;
        await api(`/api/sources/${id}`, { method: "DELETE" });
        toast("Источник удалён");
      }
      await loadSources();
      await loadEntries();
    } catch (error) {
      errorToast(error);
    } finally {
      button.disabled = false;
    }
  });

  $("#source-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const data = Object.fromEntries(new FormData(form));
    data.refresh_interval_minutes = Number(data.refresh_interval_minutes);
    const button = form.querySelector("button[type=submit]");

    button.disabled = true;
    try {
      const source = await api("/api/sources", { method: "POST", body: data });
      if (source.refresh_error) {
        toast(source.refresh_error, "err");
      } else {
        toast(`Источник «${source.name}» добавлен`);
      }
      form.reset();
      form.elements.refresh_interval_minutes.value = "60";
      await loadSources();
      await loadEntries();
    } catch (error) {
      errorToast(error);
    } finally {
      button.disabled = false;
    }
  });

  $("#upload-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const button = form.querySelector("button[type=submit]");
    const formData = new FormData(form);

    button.disabled = true;
    try {
      const source = await api("/api/sources/upload", {
        method: "POST",
        body: formData,
      });
      if (source.refresh_error) {
        toast(source.refresh_error, "err");
      } else {
        toast(`Файл «${source.name}» загружен`);
      }
      form.reset();
      await loadSources();
      await loadEntries();
    } catch (error) {
      errorToast(error);
    } finally {
      button.disabled = false;
    }
  });

  $("#refresh-all").addEventListener("click", async (event) => {
    const button = event.currentTarget;
    button.disabled = true;
    button.textContent = "Обновляем…";
    try {
      const data = await api("/api/sources/refresh-all", { method: "POST" });
      const failed = data.results.filter((item) => !item.ok);
      if (failed.length) {
        toast(
          `Не удалось обновить: ${failed.map((item) => item.name).join(", ")}`,
          "err",
        );
      } else {
        toast(`Обновлено источников: ${data.results.length}`);
      }
      await loadSources();
      await loadEntries();
    } catch (error) {
      errorToast(error);
    } finally {
      button.disabled = false;
      button.textContent = "Обновить все";
    }
  });

  // ------------------------------------------------------------- entries

  async function loadEntries() {
    const params = new URLSearchParams();
    if (state.filters.search) params.set("search", state.filters.search);
    if (state.filters.kind) params.set("kind", state.filters.kind);
    if (state.filters.source) params.set("source", state.filters.source);
    if (state.filters.enabled !== "") {
      params.set("enabled", state.filters.enabled === "1" ? "true" : "false");
    }
    params.set("limit", String(state.entries.limit));
    params.set("offset", String(state.entries.offset));

    const data = await api(`/api/entries?${params.toString()}`);
    state.entries.items = data.items;
    state.entries.total = data.total;
    state.selected.clear();

    if (!data.items.length && data.total > 0 && state.entries.offset > 0) {
      state.entries.offset = Math.max(0, state.entries.offset - state.entries.limit);
      return loadEntries();
    }

    renderEntries();
    renderPager();
    updateBulkButtons();
  }

  function renderEntries() {
    const body = $("#entries-body");
    const items = state.entries.items;

    if (!items.length) {
      body.innerHTML = `<tr><td colspan="7" class="empty">Записей нет</td></tr>`;
    } else {
      body.innerHTML = items.map((entry) => `
        <tr>
          <td class="check">
            <input type="checkbox" data-select="${entry.id}"
              ${state.selected.has(entry.id) ? "checked" : ""}
              aria-label="Выбрать ${escapeHtml(entry.normalized)}">
          </td>
          <td class="mono">${escapeHtml(entry.normalized)}</td>
          <td><span class="badge">${escapeHtml(entry.kind)}</span></td>
          <td>${escapeHtml(entry.source_name || "ручная")}</td>
          <td>
            <input type="checkbox" data-toggle="${entry.id}"
              ${entry.enabled ? "checked" : ""}
              aria-label="Включить ${escapeHtml(entry.normalized)}">
          </td>
          <td class="muted">${escapeHtml(entry.comment || "")}</td>
          <td class="actions">
            <button class="danger" type="button" data-delete="${entry.id}">Удалить</button>
          </td>
        </tr>
      `).join("");
    }

    $("#entries-count").textContent = `Всего: ${state.entries.total}`;
    $("#select-all").checked =
      items.length > 0 && items.every((entry) => state.selected.has(entry.id));
  }

  function renderPager() {
    const { total, limit, offset } = state.entries;
    const from = total === 0 ? 0 : offset + 1;
    const to = Math.min(offset + limit, total);
    $("#page-info").textContent = `${from}–${to} из ${total}`;
    $("#page-prev").disabled = offset <= 0;
    $("#page-next").disabled = offset + limit >= total;
  }

  function updateBulkButtons() {
    const disabled = state.selected.size === 0;
    ["#bulk-enable", "#bulk-disable", "#bulk-delete"].forEach((selector) => {
      $(selector).disabled = disabled;
    });
  }

  $("#entries-body").addEventListener("change", async (event) => {
    const target = event.target;

    if (target.matches("input[data-select]")) {
      const id = Number(target.dataset.select);
      if (target.checked) state.selected.add(id);
      else state.selected.delete(id);
      updateBulkButtons();
      $("#select-all").checked =
        state.entries.items.length > 0 &&
        state.entries.items.every((entry) => state.selected.has(entry.id));
      return;
    }

    if (target.matches("input[data-toggle]")) {
      try {
        await api(`/api/entries/${target.dataset.toggle}`, {
          method: "PATCH",
          body: { enabled: target.checked },
        });
        await loadStats();
      } catch (error) {
        target.checked = !target.checked;
        errorToast(error);
      }
    }
  });

  $("#entries-body").addEventListener("click", async (event) => {
    const button = event.target.closest("button[data-delete]");
    if (!button) return;
    try {
      await api(`/api/entries/${button.dataset.delete}`, { method: "DELETE" });
      toast("Запись удалена");
      await loadEntries();
      await loadStats();
    } catch (error) {
      errorToast(error);
    }
  });

  $("#select-all").addEventListener("change", (event) => {
    state.selected.clear();
    if (event.target.checked) {
      state.entries.items.forEach((entry) => state.selected.add(entry.id));
    }
    renderEntries();
    updateBulkButtons();
  });

  async function runBulk(action) {
    if (!state.selected.size) return;
    if (
      action === "delete" &&
      !confirm(`Удалить выбранные записи (${state.selected.size})?`)
    ) {
      return;
    }
    try {
      const data = await api("/api/entries/bulk", {
        method: "POST",
        body: { ids: [...state.selected], action },
      });
      toast(`Изменено записей: ${data.changed}`);
      await loadEntries();
      await loadStats();
    } catch (error) {
      errorToast(error);
    }
  }

  $("#bulk-enable").addEventListener("click", () => runBulk("enable"));
  $("#bulk-disable").addEventListener("click", () => runBulk("disable"));
  $("#bulk-delete").addEventListener("click", () => runBulk("delete"));

  $("#entry-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const data = Object.fromEntries(new FormData(form));
    data.comment = data.comment || null;

    try {
      const result = await api("/api/entries", { method: "POST", body: data });
      const parts = [`Добавлено: ${result.created}`];
      if (result.duplicates) parts.push(`дубликатов: ${result.duplicates}`);
      if (result.skipped.length) parts.push(`пропущено: ${result.skipped.length}`);
      toast(parts.join(", "));
      form.reset();
      await loadEntries();
      await loadStats();
    } catch (error) {
      errorToast(error);
    }
  });

  function applyFilters() {
    state.filters = {
      search: $("#filter-search").value.trim(),
      kind: $("#filter-kind").value,
      source: $("#filter-source").value,
      enabled: $("#filter-enabled").value,
    };
    state.entries.offset = 0;
    loadEntries().catch(errorToast);
  }

  $("#filter-apply").addEventListener("click", applyFilters);
  $("#filter-search").addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      applyFilters();
    }
  });
  ["#filter-kind", "#filter-source", "#filter-enabled"].forEach((selector) => {
    $(selector).addEventListener("change", applyFilters);
  });

  $("#page-prev").addEventListener("click", () => {
    state.entries.offset = Math.max(0, state.entries.offset - state.entries.limit);
    loadEntries().catch(errorToast);
  });

  $("#page-next").addEventListener("click", () => {
    state.entries.offset += state.entries.limit;
    loadEntries().catch(errorToast);
  });

  // -------------------------------------------------------------- export

  function applySettings(values) {
    $("#list-name").value = values.list_name || "";
    $("#wildcard-policy").value = values.wildcard_policy || "skip";
    $("#include-pbr").checked = Boolean(values.include_pbr);
    $("#vpn-gateway").value = values.vpn_gateway || "";
    $("#routing-table").value = values.routing_table || "";
    $("#connection-mark").value = values.connection_mark || "";
    $("#routing-mark").value = values.routing_mark || "";
    $("#local-networks").value = values.local_networks_list || "";
  }

  function renderReadonly(readonly) {
    $("#readonly-settings").innerHTML = `
      <dt>Пользователь</dt><dd>${escapeHtml(readonly.username)}</dd>
      <dt>Basic-аутентификация</dt><dd>${readonly.auth_enabled ? "включена" : "выключена"}</dd>
      <dt>Токен экспорта</dt><dd>${readonly.export_token_enabled ? "задан" : "не задан"}</dd>
      <dt>Версия</dt><dd>${escapeHtml(readonly.version)}</dd>
    `;
  }

  function renderImportHint() {
    const base = window.location.origin;
    const token = state.readonly.export_token_enabled ? "?token=<EXPORT_TOKEN>" : "";
    $("#import-hint").textContent =
      `/tool fetch url="${base}/export.rsc${token}" dst-path=rscforge.rsc\n` +
      `/import file-name=rscforge.rsc`;
  }

  async function loadSettings() {
    const data = await api("/api/settings");
    state.settings = data.values;
    state.readonly = data.readonly;
    applySettings(data.values);
    renderReadonly(data.readonly);
    renderImportHint();
  }

  $("#export-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const payload = {
      list_name: $("#list-name").value.trim(),
      wildcard_policy: $("#wildcard-policy").value,
      include_pbr: $("#include-pbr").checked,
      vpn_gateway: $("#vpn-gateway").value.trim(),
      routing_table: $("#routing-table").value.trim(),
      connection_mark: $("#connection-mark").value.trim(),
      routing_mark: $("#routing-mark").value.trim(),
      local_networks_list: $("#local-networks").value.trim(),
    };

    try {
      const data = await api("/api/settings", { method: "PATCH", body: payload });
      state.settings = data.values;
      state.readonly = data.readonly;
      toast("Настройки сохранены");
      await loadPreview();
    } catch (error) {
      errorToast(error);
    }
  });

  async function loadPreview() {
    const data = await api("/api/export/preview");
    $("#export-preview").textContent = data.content;

    const stats = data.stats;
    const parts = [
      `К экспорту: ${stats.exported}`,
      `домены: ${stats.resolved_domains}/${stats.domains}`,
      `IP из доменов: ${stats.resolved_ips}`,
      `ip/cidr: ${stats.ip_entries}`,
    ];
    if (stats.unresolved_domains) {
      parts.push(`не разрешено: ${stats.unresolved_domains}`);
    }
    if (stats.skipped_wildcards) {
      parts.push(`пропущено wildcard: ${stats.skipped_wildcards}`);
    }
    if (stats.include_pbr) parts.push("PBR включён");
    $("#export-stats").textContent = parts.join(" · ");
  }

  $("#preview-btn").addEventListener("click", () => {
    loadPreview().catch(errorToast);
  });

  // ---------------------------------------------------------------- init

  async function init() {
    try {
      await Promise.all([loadSources(), loadEntries(), loadSettings()]);
      await loadPreview();
    } catch (error) {
      errorToast(error);
    }
  }

  init();
})();
