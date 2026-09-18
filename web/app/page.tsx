const capabilities = [
  ["课程资料", "教师上传教材和课件，系统保留版本、章节和原始位置。"],
  ["可信答疑", "回答主要依据课程资料，并提供可点击的教材引用。"],
  ["引导学习", "AI按诊断、提示、练习和总结逐步帮助学生理解。"],
];

export default function Home() {
  return (
    <main className="content">
      <section className="hero">
        <span className="eyebrow">FOUNDATION · V0.1</span>
        <h1>把教材变成可验证、可引导的学习过程</h1>
        <p className="lead">基础框架已经建立。接下来将依次加入课程、教材解析、知识库、AI教师、题目教练和学习记忆。</p>
      </section>
      <section className="grid" aria-label="平台核心能力">
        {capabilities.map(([title, description]) => (
          <article className="card" key={title}>
            <span className="badge">规划中</span>
            <h2>{title}</h2>
            <p>{description}</p>
          </article>
        ))}
      </section>
    </main>
  );
}

