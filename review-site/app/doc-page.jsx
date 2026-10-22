// 长文档页：左侧目录 + 正文
export default function DocPage({ html, toc, source }) {
  return (
    <main className="wrap">
      <div className="doc-layout">
        <aside className="toc" aria-label="目录">
          {toc.map((t) => <a key={t.id} href={`#${t.id}`} className={t.depth === 3 ? "l3" : ""}>{t.text}</a>)}
        </aside>
        <article className="prose">
          <div dangerouslySetInnerHTML={{ __html: html }} />
          {source && <p className="faint" style={{ marginTop: 32 }}>源文件：<code>{source}</code></p>}
        </article>
      </div>
    </main>
  );
}
