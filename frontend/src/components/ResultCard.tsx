import { normalize, terms } from "../text";
import { formatScore, scoreLabel } from "../format";
import type { Hit, Query } from "../models";

function Highlight({ text, words }: { text: string; words: Set<string> }) {
  return <>{text.split(/([\p{L}\p{N}]+)/u).map((part, index) =>
    words.has(normalize(part)) ? <mark key={index}>{part}</mark> : part,
  )}</>;
}

const origins = {
  original: "Аннотация источника",
  generated: "Аннотация · составлена автоматически",
  unknown: "Аннотация · происхождение не указано",
  missing: "Аннотация отсутствует",
};

export function ResultCard({ hit, query, onAttach }: {
  hit: Hit; query: Query; onAttach: (hit: Hit) => void;
}) {
  const queryWords = terms(query.title + " " + (query.annotation ?? ""));
  const words = new Set([...terms(hit.title)].filter((word) => queryWords.has(word)));
  return <li className="result">
    <div className="result-top">
      <div>
        <h3>{hit.title}</h3>
        <p className="metadata">{[hit.metadata.year, hit.metadata.department].filter(Boolean).join(" · ") || "Метаданные не указаны"}</p>
      </div>
      <div className="score">
        <strong>{formatScore(hit.score, hit.score_type)}</strong>
        <small>{scoreLabel[hit.score_type]}</small>
      </div>
    </div>
    <details className="comparison">
      <summary>
        <span className="when-closed">Сравнить</span>
        <span className="when-open">Свернуть сравнение</span>
        <span className="sr-only"> — {hit.title}</span>
      </summary>
      <div className="compare-body">
        <div className="parallel">
          <section>
            <h4>Проверяемая тема</h4>
            <p className="pair-title"><Highlight text={query.title} words={words} /></p>
            <p className="annotation-note">{query.annotation ? "Аннотация темы" : "Аннотация не добавлена"}</p>
            {query.annotation && <p className="pair-annotation"><Highlight text={query.annotation} words={words} /></p>}
          </section>
          <section>
            <h4>Тема из каталога</h4>
            <p className="pair-title"><Highlight text={hit.title} words={words} /></p>
            <p className="annotation-note">{origins[hit.annotation_origin]}</p>
            {hit.annotation && <p className="pair-annotation">{hit.annotation}</p>}
            {hit.metadata.source_url && <a className="source-link" href={hit.metadata.source_url}
              target="_blank" rel="noopener noreferrer" referrerPolicy="no-referrer">Открыть источник</a>}
          </section>
        </div>
        <p className="explanation hint">Общие слова выделены для сравнения формулировок.</p>
        <button type="button" className="text-button" onClick={() => onAttach(hit)}>Прикрепить к моей работе</button>
      </div>
    </details>
  </li>;
}
