// 検索とSNSのための情報（要件定義書 SE-03、SE-07、NF-07）：構造化データ（JSON-LD）と、作成者の表示。
// 作成者は、運営者（/about/ の「運営者」）。名称は /about/ と同じにする
export const SITE_NAME = 'SemiCompass';
export const AUTHOR = { name: 'hysd（SemiCompass運営者）', path: '/about/' };

export type SchemaType = 'NewsArticle' | 'Article' | 'DefinedTerm';

const abs = (path: string, site: URL) => new URL(path, site).href;

/** パンくずリスト（BreadcrumbList）。最後の項目（今のページ）は、正規のURLを使う */
export function breadcrumbLd(items: { label: string; href?: string }[], canonical: string, site: URL) {
  return {
    '@context': 'https://schema.org',
    '@type': 'BreadcrumbList',
    itemListElement: items.map((item, i) => ({
      '@type': 'ListItem',
      position: i + 1,
      name: item.label,
      item: item.href ? abs(item.href, site) : canonical,
    })),
  };
}

export function organizationLd(site: URL) {
  return {
    '@context': 'https://schema.org',
    '@type': 'Organization',
    name: SITE_NAME,
    url: abs('/', site),
    logo: abs('/favicon.svg', site),
  };
}

export function websiteLd(site: URL) {
  return {
    '@context': 'https://schema.org',
    '@type': 'WebSite',
    name: SITE_NAME,
    alternateName: 'セミコンパス',
    url: abs('/', site),
    inLanguage: 'ja',
    publisher: { '@type': 'Organization', name: SITE_NAME, url: abs('/', site) },
  };
}

/** 解説のページの構造化データ。記事（NewsArticle、Article）と、用語（DefinedTerm） */
export function contentLd(
  type: SchemaType,
  page: { headline: string; description: string; url: string; published?: string; modified?: string },
  site: URL,
) {
  const author = { '@type': 'Person', name: AUTHOR.name, url: abs(AUTHOR.path, site) };
  if (type === 'DefinedTerm') {
    return {
      '@context': 'https://schema.org',
      '@type': 'DefinedTerm',
      name: page.headline,
      description: page.description,
      url: page.url,
      inDefinedTermSet: { '@type': 'DefinedTermSet', name: `${SITE_NAME} 用語集`, url: abs('/glossary/', site) },
    };
  }
  return {
    '@context': 'https://schema.org',
    '@type': type,
    headline: page.headline.slice(0, 110),
    description: page.description,
    url: page.url,
    mainEntityOfPage: page.url,
    inLanguage: 'ja',
    ...(page.published ? { datePublished: page.published } : {}),
    ...(page.published || page.modified ? { dateModified: page.modified ?? page.published } : {}),
    author,
    publisher: { '@type': 'Organization', name: SITE_NAME, url: abs('/', site), logo: { '@type': 'ImageObject', url: abs('/favicon.svg', site) } },
    image: abs('/og-default.png', site),
  };
}
