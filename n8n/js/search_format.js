// search_help_center result: text for the model plus structured article ids for logging.
const rows = $input.all().map(i => i.json).filter(r => r.article_id);
if (!rows.length) {
  return [{ json: { response: 'NO_RESULTS: The help center has no article about this.', articles: [] } }];
}
const text = rows.map(r => `[${r.article_id}] ${r.title}\n${r.content}`).join('\n\n---\n\n');
return [{
  json: {
    response: 'Help center results. Cite the exact title of any article you use; ' +
      "if none of them answers the question, say you don't have that information and cite nothing.\n\n" + text,
    articles: rows.map(r => ({ id: r.article_id, title: r.title, similarity: Number(Number(r.similarity).toFixed(3)) })),
  },
}];
