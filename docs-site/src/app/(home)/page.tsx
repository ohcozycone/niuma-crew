import Link from 'next/link';
import { ArrowRight, ArrowUpRight, BookOpen } from 'lucide-react';
import pageIndex from '@generated/page-index.json';
import { PlatformEntry } from '@/components/platform-entry';
import { docSections } from '@/lib/docs-navigation';

const topics = [
  'development/architecture',
  'development/conversation',
  'development/tools',
  'development/execution',
  'development/retrieval',
  'development/evaluation',
] as const;
const pathDetails = {
  platform: {
    description: '从组织资产和员工设计，理解共享能力怎样形成。',
    action: '了解建设思路',
  },
  development: {
    description: '沿架构和对话流程，研究执行、检索与评估。',
    action: '阅读系统架构',
  },
  usage: {
    description: '配置共享员工、准备资料，启动和维护平台。',
    action: '完成首次对话',
  },
};
const paths = docSections.map((section) => ({
  title: section.title,
  href: section.url,
  icon: section.icon,
  ...pathDetails[section.id],
}));
export default function HomePage() {
  return (
    <div className="docs-home" id="main-content">
      <section className="home-intro" aria-labelledby="home-title">
        <div className="home-intro-copy">
          <h1 id="home-title">数字员工平台文档</h1>
          <p>
            把个人积累的方法、工具使用经验和知识，沉淀为多人可用的共享员工。
            围绕最小能力装配，通过实际建设理解智能体的执行机制与边界。
          </p>
          <div className="home-actions">
            <Link className="primary-link" href="/docs/start">
              了解平台建设
            </Link>
            <PlatformEntry />
          </div>
        </div>
        <aside className="start-guide" aria-labelledby="start-guide-title">
          <div className="start-guide-heading">
            <img src="/brand/mark.svg" width={44} height={44} alt="" />
            <h2 id="start-guide-title">从个人积累到共同复用</h2>
          </div>
          <ol>
            <li>
              <span className="step-number">1</span>
              <div>
                <strong>整理工作经验</strong>
                <p>明确适用任务、方法和必要资料。</p>
              </div>
            </li>
            <li>
              <span className="step-number">2</span>
              <div>
                <strong>装配最小能力</strong>
                <p>围绕成果选择技能、知识与工具操作。</p>
              </div>
            </li>
            <li>
              <span className="step-number">3</span>
              <div>
                <strong>共同使用并改进</strong>
                <p>共享同一员工，用结果检验配置。</p>
              </div>
            </li>
          </ol>
          <Link href="/docs/start/assets">
            组织资产与建设方向 <ArrowRight size={15} />
          </Link>
        </aside>
      </section>
      <section className="reader-paths" aria-labelledby="reader-title">
        <h2 id="reader-title">阅读入口</h2>
        <div className="path-grid">
          {paths.map(({ title, description, href, action, icon: Icon }) => (
            <Link href={href} key={href} className="reader-path">
              <Icon size={21} strokeWidth={1.7} />
              <h3>{title}</h3>
              <p>{description}</p>
              <span>
                {action}
                <ArrowRight size={15} />
              </span>
            </Link>
          ))}
        </div>
      </section>
      <section className="chapter-section" aria-labelledby="chapters-title">
        <div className="section-heading">
          <h2 id="chapters-title">技术专题</h2>
          <Link href="/docs/start/features">
            当前范围 <ArrowUpRight size={14} />
          </Link>
        </div>
        <div className="chapter-grid">
          {topics.map((slug) => {
            const { title, description } = pageIndex[slug];
            return (
              <Link href={`/docs/${slug}`} key={slug} className="chapter-link">
                <BookOpen size={19} strokeWidth={1.6} />
                <div>
                  <h3>{title}</h3>
                  <p>{description}</p>
                </div>
                <ArrowRight className="chapter-arrow" size={17} />
              </Link>
            );
          })}
        </div>
      </section>
      <footer className="home-footer">
        <span>NiumaCrew · 数字员工平台</span>
        <span>{docSections.map((section) => section.title).join(' · ')}</span>
      </footer>
    </div>
  );
}
