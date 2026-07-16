import type { Metadata } from 'next';
import { Inspector } from 'react-dev-inspector';
import './globals.css';

export const metadata: Metadata = {
  title: {
    default: '宝宝辅食食谱大全 | 0-3岁宝宝辅食推荐',
    template: '%s | 宝宝辅食食谱',
  },
  description:
    '为0-3岁宝宝提供科学营养的辅食食谱推荐，内置100道专业辅食食谱，按月龄、分类、食材等多维度筛选，助力宝宝健康成长。',
  keywords: [
    '宝宝辅食',
    '婴儿食谱',
    '辅食推荐',
    '0-3岁',
    '宝妈',
    '宝宝营养',
    '辅食大全',
  ],
  robots: {
    index: true,
    follow: true,
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const isDev = process.env.COZE_PROJECT_ENV === 'DEV';

  return (
    <html lang="zh-CN">
      <body className={`antialiased`}>
        {isDev && <Inspector />}
        {children}
      </body>
    </html>
  );
}
