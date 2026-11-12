const stopWords = new Set("и или а но в во на по у из за к ко о об от для до при с со без под над между через как".split(" "));

export function normalize(text: string): string {
  return text.normalize("NFKC").toLocaleLowerCase("ru").replaceAll("ё", "е");
}

export function terms(text: string): Set<string> {
  return new Set((normalize(text).match(/[\p{L}\p{N}]+/gu) ?? []).filter((word) => !stopWords.has(word)));
}
