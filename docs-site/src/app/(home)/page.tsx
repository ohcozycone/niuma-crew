import { publicPath } from '@/lib/public-path';
import Link from 'next/link';
import {
  ArrowRight,
  ArrowUpRight,
  BookOpen,
  Code2,
  Compass,
  ListChecks,
  Server,
  CircleHelp,
  MessageSquare,
  Settings2,
} from 'lucide-react';

const chapters = [
  {
    title: '快速开始',
    description: '认识平台，完成第一次对话。',
    href: '/docs/start',
    icon: Compass,
  },
  {
    title: '使用指南',
    description: '员工、技能、工具、知识与交付。',
    href: '/docs/usage/agents',
    icon: BookOpen,
  },
  {
    title: '实操教程',
    description: '从配置到验证，走通完整链路。',
    href: '/docs/tutorials/first-agent',
    icon: ListChecks,
  },
  {
    title: '部署与维护',
    description: '启动服务，管理配置和持久数据。',
    href: '/docs/deployment/local',
    icon: Server,
  },
  {
    title: '开发指南',
    description: '理解架构，找到代码与接口入口。',
    href: '/docs/development/architecture',
    icon: Code2,
  },
  {
    title: '常见问题',
    description: '从具体问题找到排查与恢复方法。',
    href: '/docs/help/troubleshooting',
    icon: CircleHelp,
  },
];
const paths = [
  {
    title: '我要使用员工',
    description: '选择一位员工，交办一件具体的工作。',
    href: '/docs/start/first-conversation',
    action: '开始第一次对话',
    icon: MessageSquare,
  },
  {
    title: '我要配置平台',
    description: '准备模型连接、岗位职责与工作能力。',
    href: '/docs/tutorials/first-agent',
    action: '配置第一个员工',
    icon: Settings2,
  },
  {
    title: '我要参与开发',
    description: '从整体架构进入模块、代码与工程约定。',
    href: '/docs/development/architecture',
    action: '了解系统架构',
    icon: Code2,
  },
];
export default function HomePage() {
  return (
    <div className="docs-home" id="main-content">
      <section className="home-intro" aria-labelledby="home-title">
        <div className="home-intro-copy">
          <h1 id="home-title">
            把工作交给数字员工，
            <br />
            <span>从这里开始。</span>
          </h1>
          <p>
            为岗位明确职责，为员工装配能力。
            <br className="desktop-break" />
            从第一次对话到工具接入、知识检索与平台部署，
            <br className="desktop-break" />
            在这里找到下一步。
          </p>
          <div className="home-actions">
            <Link className="primary-link" href="/docs/start/first-conversation">
              快速上手 <ArrowRight size={16} />
            </Link>
            <Link className="quiet-link" href="/docs/start">
              了解牛马平台 <ArrowUpRight size={15} />
            </Link>
          </div>
        </div>
        <aside className="start-guide" aria-labelledby="start-guide-title">
          <div className="start-guide-heading">
            <img src={publicPath('/brand/mark.svg')} width={44} height={44} alt="" />
            <h2 id="start-guide-title">从一个具体需求开始</h2>
          </div>
          <ol>
            <li>
              <span className="step-number">1</span>
              <div>
                <strong>选对岗位</strong>
                <p>找到职责和能力适合的数字员工。</p>
              </div>
            </li>
            <li>
              <span className="step-number">2</span>
              <div>
                <strong>交代清楚</strong>
                <p>说明目标，提供需要的材料与方法。</p>
              </div>
            </li>
            <li>
              <span className="step-number">3</span>
              <div>
                <strong>取得成果</strong>
                <p>查看实际执行，阅读回复并核对交付。</p>
              </div>
            </li>
          </ol>
          <Link href="/docs/start/first-conversation">
            跟着指南完成第一次对话 <ArrowRight size={15} />
          </Link>
        </aside>
      </section>
      <section className="reader-paths" aria-labelledby="reader-title">
        <h2 id="reader-title">找到你的起点</h2>
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
          <h2 id="chapters-title">逐步了解牛马平台</h2>
          <Link href="/docs/help/troubleshooting">
            遇到问题？
            <ArrowUpRight size={14} />
          </Link>
        </div>
        <div className="chapter-grid">
          {chapters.map(({ title, description, href, icon: Icon }) => (
            <Link href={href} key={href} className="chapter-link">
              <Icon size={19} strokeWidth={1.6} />
              <div>
                <h3>{title}</h3>
                <p>{description}</p>
              </div>
              <ArrowRight className="chapter-arrow" size={17} />
            </Link>
          ))}
        </div>
      </section>
      <footer className="home-footer">
        <span>NiumaCrew · 数字员工平台</span>
        <span>明确职责，装配能力，交付工作。</span>
      </footer>
    </div>
  );
}
