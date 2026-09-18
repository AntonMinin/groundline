import { CONTENT, SITE } from './content.js'

const origin = (site) => (site ? site.origin : 'https://groundline.antonmb.com')

export function organization(site) {
  return {
    '@context': 'https://schema.org',
    '@type': 'Organization',
    '@id': `${origin(site)}/#organization`,
    name: SITE.name,
    url: origin(site),
    logo: `${origin(site)}/og.png`,
    founder: { '@type': 'Person', name: SITE.author },
    sameAs: [SITE.repoUrl],
  }
}

export function website(site, locale) {
  const copy = CONTENT[locale]
  return {
    '@context': 'https://schema.org',
    '@type': 'WebSite',
    '@id': `${origin(site)}/#website`,
    url: origin(site),
    name: SITE.name,
    description: copy.description,
    inLanguage: locale,
    publisher: { '@id': `${origin(site)}/#organization` },
  }
}

export function softwareApplication(site, locale) {
  const copy = CONTENT[locale]
  return {
    '@context': 'https://schema.org',
    '@type': 'SoftwareApplication',
    '@id': `${origin(site)}/#app`,
    name: SITE.name,
    url: SITE.appUrl,
    applicationCategory: 'BusinessApplication',
    applicationSubCategory: 'Retrieval-augmented generation',
    operatingSystem: 'Any modern browser',
    description: copy.description,
    inLanguage: locale,
    author: { '@type': 'Person', name: SITE.author },
    codeRepository: SITE.repoUrl,
    offers: { '@type': 'Offer', price: '0', priceCurrency: 'USD' },
    featureList: copy.how.steps.map((_, index) => copy.how.steps[index].split('.')[0]),
  }
}

export function breadcrumbs(site, locale, trail) {
  return {
    '@context': 'https://schema.org',
    '@type': 'BreadcrumbList',
    itemListElement: trail.map((item, index) => ({
      '@type': 'ListItem',
      position: index + 1,
      name: item.name,
      item: new URL(item.path, origin(site) + '/').href,
    })),
  }
}

export function faq(site, locale) {
  return {
    '@context': 'https://schema.org',
    '@type': 'FAQPage',
    inLanguage: locale,
    mainEntity: CONTENT[locale].faq.items.map(([question, answer]) => ({
      '@type': 'Question',
      name: question,
      acceptedAnswer: { '@type': 'Answer', text: answer },
    })),
  }
}
