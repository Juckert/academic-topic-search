import { useState } from "react";
import { formatDate, formatScore, scoreLabel, scopeText } from "../format";
import type { Draft, HistoryEntry, Settings } from "../models";

export function HistoryPage({ entries, keepHistory, saving, onOpen, onRemove }: {
  entries: HistoryEntry[]; keepHistory: boolean; saving: boolean;
  onOpen: (entry: HistoryEntry, repeat: boolean) => void; onRemove: (id: string) => void;
}) {
  return <>
    <h1 id="history-heading" tabIndex={-1}>История проверок</h1>
    <p className="intro">Откройте результаты предыдущей проверки или запустите её снова.</p>
    <div className="collection">
      {entries.length ? <ul className="result-list">{entries.map((entry) => <li className="library-row" key={entry.id}>
        <h2>{entry.query.title}</h2>
        <p className="metadata">{formatDate(entry.at)} · {scopeText(entry.query)}</p>
        <p className="hint">Кандидатов в выдаче — {entry.result.hits.length}
          {entry.result.hits[0] && " · Наибольшая оценка " + formatScore(entry.result.hits[0].score, entry.result.score_type) + " " + scoreLabel[entry.result.score_type]}</p>
        <div className="actions">
          <button type="button" className="text-button" onClick={() => onOpen(entry, false)}>Открыть</button>
          <button type="button" className="text-button" onClick={() => onOpen(entry, true)}>Повторить</button>
          <button type="button" className="text-button quiet-danger" disabled={saving} onClick={() => onRemove(entry.id)}>Удалить</button>
        </div>
      </li>)}</ul> : <p className="empty">{keepHistory ? "Здесь появится первая выполненная проверка."
        : "Сохранение новых проверок выключено в настройках профиля."}</p>}
    </div>
  </>;
}

export function WorksPage({ drafts, saving, onCreate, onEdit, onRemove, onDetach }: {
  drafts: Draft[]; saving: boolean; onCreate: () => void; onEdit: (draft: Draft, repeat: boolean) => void;
  onRemove: (id: string) => void; onDetach: (draftId: string, topicId: string) => void;
}) {
  return <>
    <div className="page-heading">
      <h1 id="works-heading" tabIndex={-1}>Мои работы</h1>
      <button type="button" className="secondary" onClick={onCreate}>Создать черновик</button>
    </div>
    <p className="intro">Сохранённые формулировки и прикреплённые к ним работы из каталога.</p>
    <div className="collection">
      {drafts.length ? <ul className="result-list">{[...drafts].sort((a, b) => b.updatedAt - a.updatedAt).map((draft) =>
        <li className="library-row" key={draft.id}>
          <h2>{draft.query.title}</h2>
          <p className="metadata">{draft.checkedAt ? "Последняя проверка · " + formatDate(draft.checkedAt) : "Ещё не проверялась"}</p>
          {draft.query.annotation && <details>
            <summary>Аннотация темы</summary><p className="draft-text">{draft.query.annotation}</p>
          </details>}
          {draft.links.length > 0 && <details>
            <summary>Прикреплённые работы · {draft.links.length}</summary>
            <ul className="attachment-list">{draft.links.map((topic) => <li key={topic.id}>
              {topic.metadata.source_url
                ? <a className="source-link" href={topic.metadata.source_url} target="_blank" rel="noopener noreferrer" referrerPolicy="no-referrer">{topic.title}</a>
                : <span className="attachment-title">{topic.title}</span>}
              <button type="button" className="text-button" disabled={saving} onClick={() => onDetach(draft.id, topic.id)}>Открепить</button>
            </li>)}</ul>
          </details>}
          <div className="actions">
            <button type="button" className="text-button" onClick={() => onEdit(draft, false)}>Редактировать</button>
            <button type="button" className="text-button" onClick={() => onEdit(draft, true)}>{draft.checkedAt ? "Проверить снова" : "Проверить"}</button>
            <button type="button" className="text-button quiet-danger" disabled={saving} onClick={() => onRemove(draft.id)}>Удалить черновик</button>
          </div>
        </li>,
      )}</ul> : <p className="empty">Создайте черновик здесь или сохраните тему на экране проверки.</p>}
    </div>
  </>;
}

export function ProfilePage({ settings, departments, saving, onSave }: {
  settings: Settings; departments: string[]; saving: boolean; onSave: (value: Settings) => void;
}) {
  const [department, setDepartment] = useState(settings.department);
  const [keepHistory, setKeepHistory] = useState(settings.keepHistory);
  const choices = [...new Set([...departments, ...(department ? [department] : [])])];
  return <>
    <h1 id="profile-heading" tabIndex={-1}>Профиль</h1>
    <p className="intro">Черновики и история хранятся в этом браузере.</p>
    <form className="panel profile-settings" onSubmit={(event) => { event.preventDefault(); onSave({ department, keepHistory }); }}>
      <h2>Настройки</h2>
      <label htmlFor="default-department">Подразделение для новых проверок</label>
      <select id="default-department" value={department ?? ""} onChange={(event) => setDepartment(event.target.value || null)}>
        <option value="">Все подразделения</option>
        {choices.map((choice) => <option key={choice}>{choice}</option>)}
      </select>
      <label className="checkbox-line"><input type="checkbox" checked={keepHistory}
        onChange={(event) => setKeepHistory(event.target.checked)} /> Сохранять историю проверок</label>
      <p className="hint">Настройка применяется к новым проверкам. Ранее сохранённые записи доступны в истории.</p>
      <div className="actions"><button type="submit" className="primary" disabled={saving}>Сохранить настройки</button></div>
    </form>
  </>;
}
