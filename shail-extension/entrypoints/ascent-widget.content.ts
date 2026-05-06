/**
 * ascent-widget.content.ts
 * Floating ascent widget on all pages.
 * - No cssInjectionMode (avoids Chrome permission prompts)
 * - All backend fetches go through background service worker (avoids
 *   mixed-content blocks when content script runs on HTTPS pages)
 * - Shows all deliverables as expandable rows with their todos
 * - Draggable, position persisted in chrome.storage.local
 */

export default defineContentScript({
  matches: ['<all_urls>'],
  runAt: 'document_idle',

  async main() {
    const STORAGE_KEY_PINNED = 'shail_pinned_ascent';
    const STORAGE_KEY_POS    = 'shail_widget_pos';
    const MONO = 'ui-monospace,"SF Mono",Menlo,monospace';

    // ── State ────────────────────────────────────────────────────────────────
    let pinnedId: string | null = null;
    let widgetHost: HTMLDivElement | null = null;
    let pos = { x: 20, y: 80 };
    let expandedDeliverables: Set<string> = new Set();

    const posResult = await browser.storage.local.get(STORAGE_KEY_POS);
    if (posResult[STORAGE_KEY_POS]) pos = posResult[STORAGE_KEY_POS] as { x: number; y: number };

    // ── Route fetches through background to avoid mixed-content blocks ────────

    async function bgFetchAscent(id: string): Promise<Record<string, unknown> | null> {
      try {
        const res = await browser.runtime.sendMessage({ type: 'FETCH_ASCENT', payload: { id } });
        if (res?.ok) return res.data as Record<string, unknown>;
        return null;
      } catch { return null; }
    }

    async function bgToggleTodo(ascentId: string, todoId: string, completed: boolean): Promise<Record<string, unknown> | null> {
      try {
        const res = await browser.runtime.sendMessage({ type: 'TOGGLE_TODO', payload: { ascentId, todoId, completed } });
        if (res?.ok) return res.data as Record<string, unknown>;
        return null;
      } catch { return null; }
    }

    // ── Types ─────────────────────────────────────────────────────────────────

    interface TodoItem { id: string; text: string; completed: boolean; }
    interface Deliverable { id: string; text: string; completed: boolean; todos: TodoItem[]; }
    interface AscentData {
      id: string; name: string; progress: number;
      todos_completed: number; todo_count: number;
      deliverables: Deliverable[];
    }

    // ── Shadow DOM creation ───────────────────────────────────────────────────

    function createWidget(): { host: HTMLDivElement; shadow: ShadowRoot; root: HTMLDivElement } {
      const host = document.createElement('div');
      host.id = 'shail-ascent-host';
      host.style.cssText = `position:fixed;left:${pos.x}px;top:${pos.y}px;z-index:2147483647;width:260px;pointer-events:all`;
      document.documentElement.appendChild(host);

      const shadow = host.attachShadow({ mode: 'open' });

      const style = document.createElement('style');
      style.textContent = `
        :host { all: initial; }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        #root {
          background: #000;
          border: 1px solid #222;
          border-radius: 10px;
          overflow: hidden;
          font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
          box-shadow: 0 8px 40px rgba(0,0,0,0.85);
          max-height: 420px;
          display: flex;
          flex-direction: column;
        }
        .header {
          padding: 9px 12px;
          border-bottom: 1px solid #1a1a1a;
          display: flex;
          align-items: center;
          gap: 8px;
          cursor: move;
          user-select: none;
          flex-shrink: 0;
        }
        .progress-side {
          width: 3px;
          background: #111;
          border-radius: 2px;
          overflow: hidden;
          margin: 0;
          flex-shrink: 0;
          align-self: stretch;
          position: relative;
        }
        .progress-fill {
          position: absolute;
          bottom: 0;
          left: 0;
          width: 100%;
          background: #22c55e;
          border-radius: 2px;
          transition: height 0.4s ease;
        }
        .deliverables { overflow-y: auto; flex: 1; }
        .del-row {
          border-bottom: 1px solid #111;
          cursor: pointer;
          user-select: none;
        }
        .del-row:last-child { border-bottom: none; }
        .del-header {
          display: flex;
          align-items: center;
          gap: 8px;
          padding: 8px 12px;
        }
        .del-check {
          width: 14px;
          height: 14px;
          border-radius: 3px;
          border: 1px solid #333;
          display: flex;
          align-items: center;
          justify-content: center;
          font-size: 8px;
          color: #000;
          flex-shrink: 0;
        }
        .del-text {
          font-size: 11px;
          color: #ccc;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
          flex: 1;
        }
        .del-arrow { font-size: 10px; color: #444; transition: transform 0.15s; flex-shrink: 0; }
        .del-arrow.open { transform: rotate(90deg); }
        .todo-list { background: #060606; }
        .todo-item {
          display: flex;
          align-items: center;
          gap: 8px;
          padding: 6px 12px 6px 28px;
          cursor: pointer;
          border-top: 1px solid #111;
        }
        .todo-item:hover { background: #0d0d0d; }
        .todo-check {
          width: 12px;
          height: 12px;
          border-radius: 2px;
          border: 1px solid #333;
          flex-shrink: 0;
          display: flex;
          align-items: center;
          justify-content: center;
          font-size: 7px;
          color: #000;
        }
        .todo-text { font-size: 10px; color: #aaa; flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        .todo-text.done { text-decoration: line-through; color: #444; }
        button { cursor: pointer; }
        .close-btn {
          background: none;
          border: none;
          color: #444;
          font-size: 15px;
          line-height: 1;
          padding: 0;
          flex-shrink: 0;
        }
        .close-btn:hover { color: #888; }
        .status-label { font-size: 9px; color: #444; font-family: ${MONO}; padding: 2px 12px 6px; flex-shrink: 0; }
        .empty { padding: 12px; font-size: 11px; color: #444; text-align: center; }
        .error { padding: 10px 12px; font-size: 10px; color: #f87171; }
      `;
      shadow.appendChild(style);

      const root = document.createElement('div');
      root.id = 'root';
      shadow.appendChild(root);

      return { host, shadow, root };
    }

    // ── Drag ─────────────────────────────────────────────────────────────────

    function makeDraggable(handle: HTMLElement, container: HTMLDivElement) {
      let startX = 0, startY = 0, origX = 0, origY = 0;
      handle.addEventListener('mousedown', (e: MouseEvent) => {
        if ((e.target as HTMLElement).closest('button')) return;
        startX = e.clientX; startY = e.clientY;
        origX = pos.x; origY = pos.y;
        const onMove = (ev: MouseEvent) => {
          pos = { x: origX + (ev.clientX - startX), y: origY + (ev.clientY - startY) };
          container.style.left = `${pos.x}px`;
          container.style.top = `${pos.y}px`;
        };
        const onUp = () => {
          document.removeEventListener('mousemove', onMove);
          document.removeEventListener('mouseup', onUp);
          browser.storage.local.set({ [STORAGE_KEY_POS]: pos });
        };
        document.addEventListener('mousemove', onMove);
        document.addEventListener('mouseup', onUp);
        e.preventDefault();
      });
    }

    // ── Render ────────────────────────────────────────────────────────────────

    function render(root: HTMLDivElement, host: HTMLDivElement, data: AscentData | null, error?: string) {
      root.innerHTML = '';

      // Header
      const header = document.createElement('div');
      header.className = 'header';
      header.innerHTML = `
        <span style="font-size:9px;color:#22c55e;font-family:${MONO};letter-spacing:.06em">● ASCENT</span>
        <span style="flex:1;font-size:12px;font-weight:600;color:#fff;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">
          ${data ? data.name : 'Loading…'}
        </span>
        <button class="close-btn" id="sw-close">×</button>
      `;
      root.appendChild(header);
      makeDraggable(header, host);

      header.querySelector('#sw-close')!.addEventListener('click', () => {
        host.remove(); widgetHost = null;
        browser.storage.local.remove(STORAGE_KEY_PINNED);
        pinnedId = null;
      });

      if (error) {
        const errEl = document.createElement('div');
        errEl.className = 'error';
        errEl.textContent = error;
        root.appendChild(errEl);
        return;
      }

      if (!data) return;

      const pct = Math.round(data.progress * 100);

      // Status label
      const statusLabel = document.createElement('div');
      statusLabel.className = 'status-label';
      statusLabel.textContent = `${data.todos_completed}/${data.todo_count} TODOS · ${pct}%`;
      root.appendChild(statusLabel);

      if (!data.deliverables.length) {
        const empty = document.createElement('div');
        empty.className = 'empty';
        empty.textContent = 'No deliverables yet.';
        root.appendChild(empty);
        return;
      }

      // Body row: vertical progress bar on left + deliverable list
      const bodyRow = document.createElement('div');
      bodyRow.style.cssText = 'display:flex;flex:1;overflow:hidden;min-height:0';

      // Vertical progress bar (progress fills from bottom to top)
      const progressSide = document.createElement('div');
      progressSide.className = 'progress-side';
      const progressFill = document.createElement('div');
      progressFill.className = 'progress-fill';
      progressFill.style.height = `${pct}%`;
      progressSide.appendChild(progressFill);
      bodyRow.appendChild(progressSide);

      // Deliverable list — reversed so lowest index (first task) is at bottom
      const delContainer = document.createElement('div');
      delContainer.className = 'deliverables';
      delContainer.style.flex = '1';

      const reversedDeliverables = [...data.deliverables].reverse();
      reversedDeliverables.forEach(del => {
        const isExpanded = expandedDeliverables.has(del.id);
        const delRow = document.createElement('div');
        delRow.className = 'del-row';

        const delHeader = document.createElement('div');
        delHeader.className = 'del-header';
        delHeader.innerHTML = `
          <div class="del-check" style="background:${del.completed ? '#22c55e' : 'transparent'};border-color:${del.completed ? '#22c55e' : '#333'}">
            ${del.completed ? '✓' : ''}
          </div>
          <span class="del-text">${del.text}</span>
          <span class="del-arrow ${isExpanded ? 'open' : ''}">›</span>
        `;
        delRow.appendChild(delHeader);

        delHeader.addEventListener('click', () => {
          if (expandedDeliverables.has(del.id)) expandedDeliverables.delete(del.id);
          else expandedDeliverables.add(del.id);
          render(root, host, data);
        });

        // Todos — also reversed (bottom-to-top climb order)
        if (isExpanded && del.todos.length > 0) {
          const todoList = document.createElement('div');
          todoList.className = 'todo-list';
          const reversedTodos = [...del.todos].reverse();
          reversedTodos.forEach(todo => {
            const todoEl = document.createElement('div');
            todoEl.className = 'todo-item';
            todoEl.innerHTML = `
              <div class="todo-check" style="background:${todo.completed ? '#fff' : 'transparent'};border-color:${todo.completed ? '#fff' : '#333'}">
                ${todo.completed ? '✓' : ''}
              </div>
              <span class="todo-text ${todo.completed ? 'done' : ''}">${todo.text}</span>
            `;
            todoEl.addEventListener('click', async (e) => {
              e.stopPropagation();
              if (!pinnedId) return;
              todoEl.style.opacity = '0.5';
              const updated = await bgToggleTodo(pinnedId, todo.id, !todo.completed);
              if (updated) render(root, host, updated as unknown as AscentData);
              else todoEl.style.opacity = '1';
            });
            todoList.appendChild(todoEl);
          });
          delRow.appendChild(todoList);
        } else if (isExpanded && del.todos.length === 0) {
          const none = document.createElement('div');
          none.style.cssText = 'padding:6px 12px 6px 28px;font-size:10px;color:#333;background:#060606';
          none.textContent = 'No todos.';
          delRow.appendChild(none);
        }

        delContainer.appendChild(delRow);
      });

      bodyRow.appendChild(delContainer);
      root.appendChild(bodyRow);
    }

    // ── Show / refresh widget ─────────────────────────────────────────────────

    async function showWidget(id: string) {
      if (widgetHost) { widgetHost.remove(); widgetHost = null; }

      const { host, root } = createWidget();
      widgetHost = host;

      // Show loading state immediately
      render(root, host, null);

      const data = await bgFetchAscent(id);
      if (!data) {
        render(root, host, null, 'Backend offline or ascent not found');
      } else {
        // Auto-expand first deliverable on initial load
        const deliverables = (data.deliverables as Deliverable[]) ?? [];
        if (deliverables.length > 0 && expandedDeliverables.size === 0) {
          expandedDeliverables.add(deliverables[0].id);
        }
        render(root, host, data as unknown as AscentData);
      }
    }

    // ── Watch pinned ascent storage ───────────────────────────────────────────

    async function checkPinned() {
      const result = await browser.storage.local.get(STORAGE_KEY_PINNED);
      const newId = (result[STORAGE_KEY_PINNED] as string) ?? null;
      if (newId === pinnedId) return;
      pinnedId = newId;
      if (!newId) {
        if (widgetHost) { widgetHost.remove(); widgetHost = null; }
      } else {
        expandedDeliverables = new Set();
        await showWidget(newId);
      }
    }

    await checkPinned();

    browser.storage.onChanged.addListener((changes, area) => {
      if (area === 'local' && STORAGE_KEY_PINNED in changes) checkPinned();
    });
  },
});
