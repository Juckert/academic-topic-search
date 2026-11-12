import { useEffect, useRef, useState } from "react";
import { loadFilters, searchMode, searchTopics } from "./api";
import { isAbort } from "./format";
import { defaultView, emptyLibrary, emptyQuery, newId, querySchema, sameText, storedQuerySchema, topicSchema } from "./models";
import type { Draft, FilterOptions, HistoryEntry, Library, Page, Query, Settings, View } from "./models";
import { readLibrary, updateLibrary } from "./storage";
import { SearchPage } from "./components/SearchPage";
import type { SearchSession } from "./components/SearchPage";
import { HistoryPage, ProfilePage, WorksPage } from "./components/Collections";
import { AttachDialog } from "./components/AttachDialog";
import type { Attachment } from "./components/AttachDialog";

const pages: Record<Page, string> = { search: "Проверка темы", history: "История проверок", works: "Мои работы", profile: "Профиль" };
const fromHash = (): Page => Object.hasOwn(pages, location.hash.slice(1)) ? location.hash.slice(1) as Page : "search";
const initialSession = (): SearchSession => ({
  query: emptyQuery(), view: { ...defaultView }, draftId: null, result: null, busy: false, snapshotAt: null,
});
function createDraft(query: Query, checkedAt: number | null = null): Draft {
  return { id: newId(), query, updatedAt: Date.now(), checkedAt, links: [] };
}
function findDraft(library: Library, id: string): Draft {
  const draft = library.drafts.find((item) => item.id === id);
  if (!draft) throw new Error("Черновик уже удалён. Выберите другую работу.");
  return draft;
}

export default function App() {
  const [page, setPage] = useState<Page>(fromHash);
  const [menuOpen, setMenuOpen] = useState(false);
  const [library, setLibrary] = useState<Library>(emptyLibrary);
  const [session, setSession] = useState<SearchSession>(initialSession);
  const [options, setOptions] = useState<FilterOptions | null>(null);
  const [ready, setReady] = useState(false);
  const [saving, setSaving] = useState(false);
  const [filterError, setFilterError] = useState("");
  const [storageWarning, setStorageWarning] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [attachment, setAttachment] = useState<Attachment | null>(null);
  const request = useRef<AbortController | null>(null);
  const requestVersion = useRef(0);
  const pendingWrites = useRef(0);
  const currentSession = useRef(session);
  currentSession.current = session;

  useEffect(() => {
    const controller = new AbortController();
    let mounted = true;
    void (async () => {
      try {
        const stored = await readLibrary();
        if (!mounted) return;
        setLibrary(stored.library);
        setStorageWarning(stored.warning);
        setSession((value) => ({ ...value, query: emptyQuery(stored.library.settings.department) }));
        try {
          const filters = await loadFilters(controller.signal);
          if (!mounted) return;
          setOptions(filters);
          if (stored.library.settings.department && !filters.departments.includes(stored.library.settings.department)) {
            setSession((value) => ({ ...value, query: emptyQuery() }));
          }
        } catch (failure) {
          if (mounted && !isAbort(failure)) {
            setFilterError(failure instanceof Error ? failure.message : "Справочники недоступны.");
            setSession((value) => ({ ...value, query: emptyQuery() }));
          }
        }
      } catch {
        if (mounted) setError("Не удалось открыть сохранённые данные.");
      } finally {
        if (mounted) setReady(true);
      }
    })();
    return () => { mounted = false; controller.abort(); };
  }, []);

  useEffect(() => {
    const changed = () => { setPage(fromHash()); setMenuOpen(false); };
    window.addEventListener("hashchange", changed);
    return () => window.removeEventListener("hashchange", changed);
  }, []);

  useEffect(() => {
    document.title = pages[page] + " · Каталог ВКР";
    setMenuOpen(false);
    setError("");
    window.scrollTo(0, 0);
    document.getElementById(page + "-heading")?.focus({ preventScroll: true });
  }, [page]);

  useEffect(() => {
    if (!notice) return;
    const timer = setTimeout(() => setNotice(""), 4500);
    return () => clearTimeout(timer);
  }, [notice]);

  useEffect(() => {
    if (page !== "search" || !session.result) return;
    const heading = document.getElementById("results-title");
    heading?.focus({ preventScroll: true });
    heading?.scrollIntoView({ block: "nearest" });
  }, [page, session.result]);

  useEffect(() => {
    const refresh = () => {
      if (document.visibilityState !== "visible") return;
      void readLibrary().then((stored) => { setLibrary(stored.library); setStorageWarning(stored.warning); })
        .catch(() => setError("Не удалось обновить сохранённые данные."));
    };
    document.addEventListener("visibilitychange", refresh);
    return () => document.removeEventListener("visibilitychange", refresh);
  }, []);

  function navigate(target: Page) {
    setPage(target);
    setMenuOpen(false);
    if (location.hash !== "#" + target) location.hash = target;
  }

  function cancelSearch() {
    request.current?.abort();
    requestVersion.current++;
  }

  function changeQuery(query: Query) {
    cancelSearch();
    setError("");
    setSession((value) => ({
      ...value, query, result: null, busy: false, snapshotAt: null,
      view: { ...value.view, minimumScore: null },
    }));
  }

  function newQuery() {
    cancelSearch();
    setSession({ ...initialSession(), query: emptyQuery(
      !options || options.departments.includes(library.settings.department ?? "") ? library.settings.department : null,
    ) });
    setError("");
    navigate("search");
    setTimeout(() => document.getElementById("topic")?.focus(), 0);
  }

  async function persist(edit: (value: Library) => void): Promise<Library | null> {
    pendingWrites.current++;
    setSaving(true);
    setError("");
    try {
      const value = await updateLibrary(edit);
      setLibrary(value);
      return value;
    } catch (failure) {
      setError(failure instanceof DOMException && failure.name === "QuotaExceededError"
        ? "Хранилище браузера заполнено. Удалите ненужные записи и повторите сохранение."
        : "Не удалось сохранить данные. Повторите действие.");
      return null;
    } finally {
      pendingWrites.current--;
      setSaving(pendingWrites.current > 0);
    }
  }

  async function runSearch(query: Query, draftId: string | null, view: View) {
    cancelSearch();
    setError("");
    const parsed = querySchema.safeParse(query);
    if (!parsed.success) {
      const field = parsed.error.issues[0]?.path[0];
      setError(field === "annotation" ? "Аннотация должна содержать не более 3498 символов."
        : "Введите название темы длиной до 500 символов.");
      setSession((value) => ({ ...value, result: null, busy: false }));
      document.getElementById(field === "annotation" ? "annotation" : "topic")?.focus();
      return;
    }
    const controller = new AbortController();
    request.current = controller;
    const version = requestVersion.current;
    const previousType = currentSession.current.result?.score_type ?? options?.score_type;
    setSession({ query: parsed.data, draftId, view, result: null, busy: true, snapshotAt: null });
    try {
      const result = await searchTopics(parsed.data, controller.signal);
      if (controller.signal.aborted || version !== requestVersion.current) return;
      const resultView = previousType && previousType !== result.score_type ? { ...view, minimumScore: null } : view;
      const entry: HistoryEntry = {
        id: newId(), at: Date.now(), query: parsed.data, view: resultView, result,
      };
      setSession({ query: parsed.data, draftId, view: resultView, result, busy: false, snapshotAt: entry.at });
      await persist((state) => {
        if (state.settings.keepHistory) state.history.unshift(entry);
        const draft = state.drafts.find((item) => item.id === draftId) ??
          state.drafts.find((item) => sameText(item.query, parsed.data));
        if (draft && sameText(draft.query, parsed.data)) draft.checkedAt = entry.at;
      });
    } catch (failure) {
      if (isAbort(failure) || version !== requestVersion.current) return;
      setError(failure instanceof Error ? failure.message : "Не удалось выполнить поиск.");
    } finally {
      if (version === requestVersion.current) setSession((value) => ({ ...value, busy: false }));
    }
  }

  async function saveDraft() {
    const value = currentSession.current;
    const query = storedQuerySchema.safeParse(value.query);
    if (!query.success) { setError("Введите название темы."); return; }
    let id = "";
    const stored = await persist((state) => {
      let draft = value.draftId ? findDraft(state, value.draftId) : state.drafts.find((item) => sameText(item.query, query.data));
      if (!draft) { draft = createDraft(query.data); state.drafts.push(draft); }
      if (!sameText(draft.query, query.data)) draft.checkedAt = null;
      draft.query = query.data;
      draft.updatedAt = Date.now();
      if (value.result) draft.checkedAt = Math.max(draft.checkedAt ?? 0, value.snapshotAt ?? Date.now());
      id = draft.id;
    });
    if (stored) {
      setSession((current) => sameText(current.query, query.data) ? { ...current, draftId: id } : current);
      setNotice("Тема сохранена в разделе «Мои работы».");
    }
  }

  function openHistory(entry: HistoryEntry, repeat: boolean) {
    cancelSearch();
    navigate("search");
    const draftId = library.drafts.find((draft) => sameText(draft.query, entry.query))?.id ?? null;
    if (repeat) {
      const view = options?.score_type === entry.result.score_type ? entry.view : { ...entry.view, minimumScore: null };
      void runSearch(entry.query, draftId, view);
    } else {
      setSession({ query: entry.query, draftId, view: entry.view, result: entry.result, busy: false, snapshotAt: entry.at });
    }
  }

  function openDraft(draft: Draft, repeat: boolean) {
    cancelSearch();
    navigate("search");
    if (repeat) void runSearch(draft.query, draft.id, { ...defaultView });
    else setSession({ ...initialSession(), query: draft.query, draftId: draft.id });
  }

  async function attachSelected(target: string) {
    if (!attachment) return;
    const value = attachment;
    let id = "";
    const stored = await persist((state) => {
      let draft = target === "new"
        ? state.drafts.find((item) => sameText(item.query, value.query))
        : findDraft(state, target);
      if (!draft) { draft = createDraft(value.query, value.at); state.drafts.push(draft); }
      if (!draft.links.some((topic) => topic.id === value.hit.id)) draft.links.push(topicSchema.parse(value.hit));
      draft.updatedAt = Date.now();
      if (sameText(draft.query, value.query)) draft.checkedAt = Math.max(draft.checkedAt ?? 0, value.at);
      id = draft.id;
    });
    if (stored) {
      const draft = findDraft(stored, id);
      setSession((current) => !current.draftId && sameText(current.query, draft.query) ? { ...current, draftId: id } : current);
      setAttachment(null);
      setNotice("Запись прикреплена к черновику.");
    }
  }

  async function saveSettings(settings: Settings) {
    const previous = library.settings.department;
    const stored = await persist((state) => { state.settings = settings; });
    if (stored) {
      if (!session.query.title && !session.draftId && session.query.filters.department === previous) {
        changeQuery(emptyQuery(settings.department));
      }
      setNotice("Настройки сохранены.");
    }
  }

  async function retryFilters() {
    try {
      setOptions(await loadFilters());
      setFilterError("");
    } catch (failure) {
      setFilterError(failure instanceof Error ? failure.message : "Справочники недоступны.");
    }
  }

  return <>
    <header className="masthead"><div className="wrap">
      <span className="brand">Каталог <span>ВКР</span></span>
      <button type="button" id="menu-button" className="secondary" aria-controls="navigation" aria-expanded={menuOpen}
        onClick={() => setMenuOpen(!menuOpen)}>Меню</button>
      <nav id="navigation" className={"navigation" + (menuOpen ? " open" : "")} aria-label="Разделы">
        {(Object.entries(pages) as [Page, string][]).map(([name, label]) =>
          <a key={name} href={"#" + name} aria-current={page === name ? "page" : undefined}
            onClick={(event) => { event.preventDefault(); navigate(name); }}>{label}</a>,
        )}
      </nav>
    </div></header>
    <main className="wrap">
      {storageWarning && <p className="notice" role="status">{storageWarning}</p>}
      {error && <p className="error" role="alert">{error}</p>}
      {page === "search" && <SearchPage session={session} options={options} drafts={library.drafts} ready={ready} saving={saving}
        mode={searchMode} filterError={filterError} onQuery={changeQuery}
        onView={(view) => setSession((value) => ({ ...value, view }))}
        onSearch={() => void runSearch(session.query, session.draftId, session.view)}
        onSave={() => void saveDraft()} onNew={newQuery} onRetryFilters={() => void retryFilters()}
        onExample={() => { changeQuery({ ...session.query, title: "Эффект налоговой нагрузки на финансовую устойчивость российских банков" });
          setSession((value) => ({ ...value, draftId: null })); }}
        onAttach={(hit) => session.result && setAttachment({
          hit, query: session.result.query, at: session.snapshotAt ?? Date.now(),
        })} />}
      {page === "history" && <HistoryPage entries={library.history} keepHistory={library.settings.keepHistory} saving={saving}
        onOpen={openHistory} onRemove={(id) => {
          if (confirm("Удалить эту проверку из истории?")) void persist((state) => { state.history = state.history.filter((entry) => entry.id !== id); });
        }} />}
      {page === "works" && <WorksPage drafts={library.drafts} saving={saving} onCreate={newQuery} onEdit={openDraft}
        onRemove={(id) => {
          if (confirm("Удалить черновик вместе с его подборкой работ?")) {
            void persist((state) => { state.drafts = state.drafts.filter((draft) => draft.id !== id); })
              .then((stored) => { if (stored) setSession((value) => value.draftId === id ? { ...value, draftId: null } : value); });
          }
        }}
        onDetach={(draftId, topicId) => {
          void persist((state) => {
            const draft = findDraft(state, draftId);
            draft.links = draft.links.filter((topic) => topic.id !== topicId);
            draft.updatedAt = Date.now();
          });
        }} />}
      {page === "profile" && ready && <ProfilePage settings={library.settings} departments={options?.departments ?? []} saving={saving}
        onSave={(settings) => void saveSettings(settings)} />}
      {notice && <p className="status-message" role="status">{notice}</p>}
    </main>
    {attachment && <AttachDialog attachment={attachment} drafts={library.drafts} activeDraftId={session.draftId} saving={saving}
      onSave={attachSelected} onClose={() => setAttachment(null)} />}
  </>;
}
