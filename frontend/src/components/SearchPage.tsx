import { limits, sameText } from "../models";
import type { Draft, FilterOptions, Hit, Query, SearchResult, View } from "../models";
import { formatDate, scoreLabel, scopeText } from "../format";
import { ResultCard } from "./ResultCard";

export interface SearchSession {
  query: Query; view: View; draftId: string | null; result: SearchResult | null;
  busy: boolean; snapshotAt: number | null;
}

export function SearchPage({ session, options, drafts, ready, saving, mode, filterError,
  onQuery, onView, onSearch, onSave, onNew, onExample, onAttach, onRetryFilters }: {
  session: SearchSession; options: FilterOptions | null; drafts: Draft[]; ready: boolean;
  saving: boolean; mode: "demo" | "api"; filterError: string;
  onQuery: (query: Query) => void; onView: (view: View) => void; onSearch: () => void;
  onSave: () => void; onNew: () => void; onExample: () => void; onAttach: (hit: Hit) => void;
  onRetryFilters: () => void;
}) {
  const { query, view, result } = session;
  const active = drafts.find((draft) => draft.id === session.draftId);
  const matching = active ?? drafts.find((draft) => sameText(draft.query, query));
  const saved = matching && sameText(matching.query, query) &&
    matching.query.filters.department === query.filters.department && matching.query.filters.year === query.filters.year;
  const type = result?.score_type ?? options?.score_type;
  const isPercentage = type === "word_overlap";
  const visible = result?.hits.filter((hit) => view.minimumScore === null ||
    (isPercentage ? Math.round(hit.score * 100) / 100 : hit.score) >= view.minimumScore) ?? [];
  const shown = visible.slice(0, view.limit);
  const filtered = Boolean(result?.hits.length && !visible.length);
  const displayedMinimum = view.minimumScore === null ? "" : isPercentage ? Math.round(view.minimumScore * 100) : view.minimumScore;
  const selectedScope = [query.filters.department, query.filters.year].filter(Boolean).join(" · ");
  const departments = [...new Set([...(options?.departments ?? []), ...(query.filters.department ? [query.filters.department] : [])])];
  const years = [...new Set([...(options?.years ?? []), ...(query.filters.year ? [query.filters.year] : [])])];
  return <>
    <h1 id="search-heading" tabIndex={-1}>Проверка темы ВКР</h1>
    <p className="intro">Найдите похожие формулировки{options ? " среди " + options.corpus_size + " тем каталога" : " в каталоге учебных работ"}.</p>
    <form className="panel" onSubmit={(event) => { event.preventDefault(); onSearch(); }} aria-busy={session.busy}>
      <div className="label-row">
        <label htmlFor="topic">Название темы</label>
        {mode === "demo" && <button type="button" className="text-button" onClick={onExample} disabled={!ready}>Подставить пример</button>}
      </div>
      <div className="search-row">
        <input id="topic" value={query.title} maxLength={limits.title} required disabled={!ready}
          placeholder="Введите название ВКР" onChange={(event) => onQuery({ ...query, title: event.target.value })} />
        <button type="submit" className="primary" disabled={!ready || session.busy}>{session.busy ? "Ищем…" : "Найти похожие темы"}</button>
      </div>
      <div className="tools-row">
        <details className="annotation-entry" key={"annotation-" + session.draftId} open={query.annotation ? true : undefined}>
          <summary>{query.annotation ? "Аннотация темы" : "Добавить аннотацию"} <span className="optional">· необязательно</span></summary>
          <label className="sr-only" htmlFor="annotation">Аннотация темы</label>
          <textarea id="annotation" value={query.annotation ?? ""} maxLength={limits.annotation} disabled={!ready}
            placeholder="Цель работы, задача и материал исследования"
            onChange={(event) => onQuery({ ...query, annotation: event.target.value || null })} />
        </details>
        <details>
          <summary>Где искать <span className="optional">{selectedScope && "· " + selectedScope}</span></summary>
          <div className="filters-grid">
            <label>Подразделение<select value={query.filters.department ?? ""} disabled={!ready || !options}
              onChange={(event) => onQuery({ ...query, filters: { ...query.filters, department: event.target.value || null } })}>
              <option value="">Все подразделения</option>
              {departments.map((department) => <option key={department}>{department}</option>)}
            </select></label>
            <label>Год<select value={query.filters.year ?? ""} disabled={!ready || !options}
              onChange={(event) => onQuery({ ...query, filters: { ...query.filters, year: event.target.value ? Number(event.target.value) : null } })}>
              <option value="">Все годы</option>
              {years.map((year) => <option key={year} value={year}>{year}</option>)}
            </select></label>
          </div>
        </details>
      </div>
      {(query.title || active) && <div className="actions query-actions">
        <span className="hint">{active ? "Черновик из раздела «Мои работы»" : ""}</span>
        <button type="button" className="text-button" disabled={saving || saved} onClick={onSave}>
          {saved ? "Тема сохранена" : active ? "Сохранить изменения" : "Сохранить мою тему"}
        </button>
        <button type="button" className="text-button" onClick={onNew}>Новая тема</button>
      </div>}
    </form>
    {mode === "demo" && <p className="demo-notice">Демонстрационный поиск по словам. {options?.dataset_id === "demo-synthetic"
      ? "Записи синтетические." : "Используется локальный каталог."}</p>}
    {filterError && <div className="notice" role="status">{filterError} Можно искать без ограничения области.{" "}
      <button type="button" className="text-button" onClick={onRetryFilters}>Повторить загрузку фильтров</button>
    </div>}
    {result && <section className="results" aria-labelledby="results-title">
      <div className="results-heading">
        <h2 id="results-title" tabIndex={-1}>Похожие темы</h2>
        <span className="count" role="status">Показано {shown.length} из {visible.length}
          {visible.length < result.hits.length && " · до фильтра " + result.hits.length}</span>
      </div>
      <p className="hint">{session.snapshotAt && "Проверка от " + formatDate(session.snapshotAt) + " · "}
        {scopeText(result.query)} · {scoreLabel[result.score_type]}
        {result.candidate_count === result.candidate_limit && " · выдача ограничена " + result.candidate_limit + " кандидатами"}</p>
      <details className="view-filters">
        <summary>Фильтры выдачи <span className="optional">{displayedMinimum !== "" && "от " + displayedMinimum + (isPercentage ? "%" : "")}</span></summary>
        <div className="filters-grid">
          <label>{isPercentage ? "Минимальное сходство по словам, %" : "Минимальная оценка " + scoreLabel[result.score_type]}
            <input type="number" value={displayedMinimum} min={isPercentage || result.score_type === "bm25" || result.score_type === "rrf" ? 0 : undefined}
              max={isPercentage ? 100 : undefined} step={isPercentage ? 1 : "any"} placeholder="Без порога"
              onChange={(event) => {
                const value = event.target.valueAsNumber;
                if (Number.isFinite(value)) onView({ ...view, minimumScore: isPercentage ? Math.max(0, Math.min(100, value)) / 100 : value });
                else if (!event.target.value) onView({ ...view, minimumScore: null });
              }} />
          </label>
          <label>Показывать работ<select value={view.limit} onChange={(event) => onView({ ...view, limit: Number(event.target.value) as View["limit"] })}>
            <option>5</option><option>10</option><option>20</option>
          </select></label>
        </div>
      </details>
      {shown.length ? <ol className="result-list">{shown.map((hit) =>
        <ResultCard key={hit.id} hit={hit} query={result.query} onAttach={onAttach} />,
      )}</ol> : <div className="empty">
        <p><strong>{filtered ? "При таком пороге подходящих работ нет."
          : result.empty_reason === "filters_or_exclusions" ? "В выбранной области нет работ."
          : "Поиск не нашёл подходящих кандидатов."}</strong></p>
        <p className="hint">{filtered ? "Уменьшите минимальную оценку." : "Измените формулировку или расширьте область поиска."}</p>
        {filtered && <button type="button" className="text-button" onClick={() => onView({ ...view, minimumScore: null })}>Сбросить порог</button>}
      </div>}
    </section>}
    <details className="about">
      <summary>О данных и оценке сходства</summary>
      <p>В демонстрационном режиме процент отражает общие слова двух текстов. В режиме API отображается оценка и шкала поискового сервиса.</p>
      <p>Происхождение аннотации указано в сравнении. Решение о содержательном пересечении требует просмотра найденных работ.</p>
    </details>
  </>;
}
