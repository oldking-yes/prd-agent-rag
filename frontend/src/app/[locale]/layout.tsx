import type { Metadata } from "next";

import { Providers } from "../providers";

export default async function LocaleLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;

  if (!locales.includes(locale as Locale)) {
    notFound();
  }

  const messages = await getMessages();

  return (
    <Providers>
      <NextIntlClientProvider messages={messages}>
        <a href="#main" className="skip-link">
          Skip to content
        </a>
        {children}
        <CookieBanner />
      </NextIntlClientProvider>
    </Providers>
  );
}
