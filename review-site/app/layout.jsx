import "./globals.css";
import Nav from "./nav";

export const metadata = { title: "视频评审台", description: "创意、分镜、资产、成片四关评审与 deepseek-flash 评审器基准测试" };

export default function RootLayout({ children }) {
  return (
    <html lang="zh-CN">
      <body>
        <header className="top">
          <div className="top-in">
            <a className="brand" href="/"><span className="brand-mark" aria-hidden="true" />视频评审台</a>
            <Nav />
          </div>
        </header>
        {children}
      </body>
    </html>
  );
}
