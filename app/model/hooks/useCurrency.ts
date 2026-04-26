"use client";

import { useState, useEffect, useCallback, useMemo } from "react";

/** Currency symbols for common currencies */
const CURRENCY_SYMBOLS: Record<string, string> = {
  USD: "$",
  EUR: "€",
  GBP: "£",
  JPY: "¥",
  CNY: "¥",
  HKD: "HK$",
  KRW: "₩",
  TWD: "NT$",
  INR: "₹",
  CAD: "C$",
  AUD: "A$",
  CHF: "CHF ",
  SEK: "kr ",
  NOK: "kr ",
  DKK: "kr ",
  SGD: "S$",
  BRL: "R$",
  ILS: "₪",
};

export function currencySymbol(code: string): string {
  return CURRENCY_SYMBOLS[code] || `${code} `;
}

/**
 * Returns true if this currency is USD (no conversion needed).
 */
export function isUSD(currency: string | undefined | null): boolean {
  return !currency || currency === "USD";
}

/**
 * Format a price with the appropriate currency symbol.
 * When showUSD is true and currency is not USD, converts using fxRate.
 */
export function formatPrice(
  price: number,
  currency: string,
  showUSD: boolean,
  fxRate: number,
  opts?: { decimals?: number; compact?: boolean }
): string {
  const decimals = opts?.decimals ?? 0;
  const compact = opts?.compact ?? false;

  if (showUSD && !isUSD(currency) && fxRate > 0) {
    // Convert to USD
    const usdPrice = price * fxRate;
    if (compact) {
      return `$${Math.round(usdPrice).toLocaleString()}`;
    }
    return `$${usdPrice.toFixed(decimals)}`;
  }

  // Native currency
  const sym = currencySymbol(currency);
  if (compact) {
    return `${sym}${Math.round(price).toLocaleString()}`;
  }
  return `${sym}${price.toFixed(decimals)}`;
}

/**
 * Format a price for large numbers (billions) with currency symbol.
 */
export function formatPriceB(
  priceB: number,
  currency: string,
  showUSD: boolean,
  fxRate: number,
): string {
  const sym = showUSD && !isUSD(currency) && fxRate > 0 ? "$" : currencySymbol(currency);
  const val = showUSD && !isUSD(currency) && fxRate > 0 ? priceB * fxRate : priceB;
  return `${sym}${val.toFixed(1)}B`;
}

/**
 * Hook to manage currency display state + FX rate fetching.
 * Only fetches FX rate for non-USD currencies.
 */
export function useCurrency(nativeCurrency: string | undefined | null) {
  const currency = nativeCurrency || "USD";
  const needsConversion = !isUSD(currency);

  const [showUSD, setShowUSD] = useState(false);
  const [fxRate, setFxRate] = useState<number>(0); // native -> USD rate
  const [fxLoading, setFxLoading] = useState(false);

  // Fetch FX rate when currency changes (only for non-USD)
  useEffect(() => {
    if (!needsConversion) {
      setFxRate(0);
      setShowUSD(false);
      return;
    }

    let cancelled = false;
    setFxLoading(true);

    fetch(`/api/fx?from=${currency}&to=USD`)
      .then(r => r.json())
      .then(data => {
        if (cancelled) return;
        if (data.rate && data.rate > 0) {
          setFxRate(data.rate);
        }
      })
      .catch(() => {})
      .finally(() => {
        if (!cancelled) setFxLoading(false);
      });

    return () => { cancelled = true; };
  }, [currency, needsConversion]);

  const toggleUSD = useCallback(() => {
    if (needsConversion) setShowUSD(prev => !prev);
  }, [needsConversion]);

  // Convenience formatter bound to current state
  const fmt = useCallback(
    (price: number, opts?: { decimals?: number; compact?: boolean }) =>
      formatPrice(price, currency, showUSD, fxRate, opts),
    [currency, showUSD, fxRate]
  );

  const fmtB = useCallback(
    (priceB: number) => formatPriceB(priceB, currency, showUSD, fxRate),
    [currency, showUSD, fxRate]
  );

  return useMemo(() => ({
    currency,
    needsConversion,
    showUSD,
    toggleUSD,
    fxRate,
    fxLoading,
    fmt,
    fmtB,
  }), [currency, needsConversion, showUSD, toggleUSD, fxRate, fxLoading, fmt, fmtB]);
}

export type CurrencyState = ReturnType<typeof useCurrency>;
