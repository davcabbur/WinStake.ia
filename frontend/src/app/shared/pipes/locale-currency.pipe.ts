import { Pipe, PipeTransform } from '@angular/core';

// Maps locale (full or language prefix) to ISO 4217 currency code
const LOCALE_CURRENCY: Record<string, string> = {
  'en-US': 'USD', 'en-CA': 'CAD', 'en-GB': 'GBP', 'en-AU': 'AUD',
  'en-NZ': 'NZD', 'en-SG': 'SGD', 'en-IE': 'EUR', 'en-ZA': 'ZAR',
  'en-IN': 'INR', 'en-PH': 'PHP',
  'es-ES': 'EUR', 'es-MX': 'MXN', 'es-AR': 'ARS', 'es-CL': 'CLP',
  'es-CO': 'COP', 'es-PE': 'PEN', 'es-UY': 'UYU', 'es-EC': 'USD',
  'es-VE': 'VES', 'es-BO': 'BOB', 'es-PY': 'PYG', 'es-GT': 'GTQ',
  'fr-FR': 'EUR', 'fr-CH': 'CHF', 'fr-CA': 'CAD', 'fr-BE': 'EUR',
  'de-DE': 'EUR', 'de-AT': 'EUR', 'de-CH': 'CHF',
  'it-IT': 'EUR', 'it-CH': 'CHF',
  'pt-BR': 'BRL', 'pt-PT': 'EUR',
  'ja-JP': 'JPY', 'zh-CN': 'CNY', 'zh-TW': 'TWD', 'zh-HK': 'HKD',
  'ko-KR': 'KRW', 'ru-RU': 'RUB', 'pl-PL': 'PLN', 'tr-TR': 'TRY',
  'nl-NL': 'EUR', 'nl-BE': 'EUR', 'sv-SE': 'SEK', 'nb-NO': 'NOK',
  'da-DK': 'DKK', 'fi-FI': 'EUR', 'el-GR': 'EUR', 'cs-CZ': 'CZK',
  'hu-HU': 'HUF', 'ro-RO': 'RON', 'bg-BG': 'BGN', 'hr-HR': 'EUR',
  'sk-SK': 'EUR', 'sl-SI': 'EUR', 'uk-UA': 'UAH', 'he-IL': 'ILS',
  'ar-SA': 'SAR', 'ar-AE': 'AED', 'ar-EG': 'EGP',
  // Language-only fallbacks
  'en': 'USD', 'es': 'EUR', 'fr': 'EUR', 'de': 'EUR', 'it': 'EUR',
  'pt': 'EUR', 'ja': 'JPY', 'zh': 'CNY', 'ko': 'KRW', 'ru': 'RUB',
  'pl': 'PLN', 'tr': 'TRY', 'nl': 'EUR', 'sv': 'SEK', 'nb': 'NOK',
  'da': 'DKK', 'fi': 'EUR', 'ar': 'USD',
};

function detectCurrency(): string {
  const locale = (typeof navigator !== 'undefined' && navigator.language) || 'en-US';
  return LOCALE_CURRENCY[locale] || LOCALE_CURRENCY[locale.split('-')[0]] || 'USD';
}

/**
 * Formats a numeric value as a local currency amount.
 *
 * Usage:
 *   {{ value | localeCurrency }}               → $5.00 / €5,00 / £5.00 …
 *   {{ value | localeCurrency:1:1 }}           → $5.5 (1 decimal)
 *   {{ value | localeCurrency:2:2:true }}      → +$5.00 (prefix + for positive)
 */
@Pipe({ name: 'localeCurrency', standalone: true, pure: true })
export class LocaleCurrencyPipe implements PipeTransform {
  private readonly locale = (typeof navigator !== 'undefined' && navigator.language) || 'en-US';
  private readonly currency = detectCurrency();

  transform(value: number, minDecimals = 2, maxDecimals = 2, showSign = false): string {
    const formatted = new Intl.NumberFormat(this.locale, {
      style: 'currency',
      currency: this.currency,
      minimumFractionDigits: minDecimals,
      maximumFractionDigits: maxDecimals,
    }).format(value);

    if (showSign && value > 0) return `+${formatted}`;
    return formatted;
  }
}
