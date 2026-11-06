import { Card } from "@/components/ui/Card";
import { BrandLogo } from "@/components/brand/BrandLogo";
import { useParams } from "react-router";
import { Link } from "react-router";
import { PageHeading } from "@/components/common/PageHeading";
import { featureGuides, type HelpTopic } from "@/pages/help/guides";
import styles from "@/pages/help/guideStyles";

export function HelpPage() {
  const { topic = "agents" } = useParams();
  if (!Object.hasOwn(featureGuides, topic))
    return (
      <main className="page-frame py-6">
        指南不存在。<Link to="/agents">返回员工目录</Link>
      </main>
    );
  const guide = featureGuides[topic as HelpTopic];
  return (
    <div className={styles.page}>
      <header className={styles.topbar}>
        <Link className={styles.brandLink} to="/">
          <BrandLogo />
        </Link>
        <span>功能指南</span>
        <Link className={styles.designLink} to="/design-system">
          design
        </Link>
      </header>
      <main className={styles.main}>
        <PageHeading title={guide.title} description={guide.description} />
        <nav className={styles.topics} aria-label="功能指南目录">
          {Object.entries(featureGuides).map(([id, item]) => (
            <Link key={id} to={`/help/${id}`} aria-current={id === topic ? "page" : undefined}>
              {item.title}
            </Link>
          ))}
        </nav>
        <Card
          as="article"
          variant="outline"
          radius="panel"
          className={styles.article}
          aria-label={`${guide.title}功能说明`}
        >
          {guide.sections.map((section, index) => (
            <section key={section.title}>
              <span className={styles.number} aria-hidden="true">
                {String(index + 1).padStart(2, "0")}
              </span>
              <div>
                <h2>{section.title}</h2>
                <p>{section.content}</p>
              </div>
            </section>
          ))}
        </Card>
        <p className={styles.note}>
          员工、技能、工具许可与对话记录保存在服务器。对话使用已装配的大脑，按许可读取技能和调用工具；代码执行还需要沙箱就绪。阅读完毕可切回原工作台继续操作。
        </p>
      </main>
    </div>
  );
}

export { HelpPage as Component };
