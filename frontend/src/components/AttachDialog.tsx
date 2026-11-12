import { useEffect, useRef, useState } from "react";
import { sameText } from "../models";
import type { Draft, Hit, Query } from "../models";

export interface Attachment { hit: Hit; query: Query; at: number }

export function AttachDialog({ attachment, drafts, activeDraftId, saving, onSave, onClose }: {
  attachment: Attachment; drafts: Draft[]; activeDraftId: string | null; saving: boolean;
  onSave: (target: string) => Promise<void>; onClose: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const matching = drafts.find((draft) => sameText(draft.query, attachment.query));
  const [target, setTarget] = useState(activeDraftId && drafts.some((draft) => draft.id === activeDraftId)
    ? activeDraftId : matching?.id ?? "new");
  const selected = drafts.find((draft) => draft.id === target);
  const linked = selected?.links.some((topic) => topic.id === attachment.hit.id);
  const titleCounts = new Map<string, number>();
  for (const draft of drafts) titleCounts.set(draft.query.title, (titleCounts.get(draft.query.title) ?? 0) + 1);
  useEffect(() => {
    const node = dialog.current!;
    node.showModal();
    return () => node.close();
  }, []);
  return <dialog ref={dialog} aria-labelledby="attach-heading" onCancel={(event) => {
    event.preventDefault(); if (!saving) onClose();
  }}>
    <form onSubmit={(event) => { event.preventDefault(); void onSave(target); }}>
      <h2 id="attach-heading">Прикрепить к моей работе</h2>
      <p>{attachment.hit.title}</p>
      <label id="attach-label" htmlFor="attach-target">Черновик</label>
      <select id="attach-target" value={target} disabled={saving} onChange={(event) => setTarget(event.target.value)}>
        {!matching && <option value="new">Создать черновик из проверяемой темы</option>}
        {drafts.map((draft) => <option value={draft.id} key={draft.id}>
          {draft.query.title}{(titleCounts.get(draft.query.title) ?? 0) > 1 ? " · " + (draft.query.annotation?.slice(0, 72) || "без аннотации") : ""}
        </option>)}
      </select>
      <p className="hint">{linked ? "Эта запись уже прикреплена к выбранному черновику."
        : selected ? selected.query.annotation?.slice(0, 160)
        : "Будет создан черновик «" + attachment.query.title + "»."}</p>
      <div className="actions">
        <button type="submit" className="primary" disabled={saving || linked}>{saving ? "Сохраняем…" : "Прикрепить"}</button>
        <button type="button" className="text-button" disabled={saving} onClick={onClose}>Отмена</button>
      </div>
    </form>
  </dialog>;
}
