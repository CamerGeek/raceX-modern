"use client";

import { useMemo, useSyncExternalStore } from "react";
import {
  getCountries,
  getCountryCallingCode,
  parsePhoneNumberFromString,
  type CountryCode,
} from "libphonenumber-js";

const DEFAULT_COUNTRY: CountryCode = "BF";
const DEFAULT_PREFERENCES = { country: DEFAULT_COUNTRY, locale: "fr" };
const supportedCountries = new Set<string>(getCountries());
let browserPreferences: { country: CountryCode; locale: string } | null = null;
const africanCountries = new Set([
  "AO", "BF", "BI", "BJ", "BW", "CD", "CF", "CG", "CI", "CM", "CV", "DJ",
  "DZ", "EG", "ER", "ET", "GA", "GH", "GM", "GN", "GQ", "GW", "KE", "KM",
  "LR", "LS", "LY", "MA", "MG", "ML", "MR", "MU", "MW", "MZ", "NA", "NE",
  "NG", "RW", "SC", "SD", "SL", "SN", "SO", "SS", "ST", "SZ", "TD", "TG",
  "TN", "TZ", "UG", "ZA", "ZM", "ZW",
]);

export type ParsedPhoneNumber = {
  countryCode: CountryCode;
  internationalNumber: string;
  nationalNumber: string;
};

function readPhonePreferences(): { country: CountryCode; locale: string } {
  const locales = navigator.languages.length ? navigator.languages : [navigator.language];
  for (const locale of locales) {
    try {
      const region = new Intl.Locale(locale).region?.toUpperCase();
      if (region && supportedCountries.has(region)) {
        return { country: region as CountryCode, locale };
      }
    } catch (error) {
      if (!(error instanceof RangeError)) throw error;
    }
  }

  return {
    country: DEFAULT_COUNTRY,
    locale: locales[0] || "fr",
  };
}

function getPhonePreferences() {
  if (typeof navigator === "undefined") return DEFAULT_PREFERENCES;
  if (!browserPreferences) browserPreferences = readPhonePreferences();
  return browserPreferences;
}

function subscribeToPhonePreferences() {
  return () => {};
}

export function usePhonePreferences() {
  return useSyncExternalStore(
    subscribeToPhonePreferences,
    getPhonePreferences,
    () => DEFAULT_PREFERENCES,
  );
}

export function parseValidPhoneNumber(
  value: string,
  defaultCountry: CountryCode,
): ParsedPhoneNumber | null {
  const parsed = parsePhoneNumberFromString(value.trim(), {
    defaultCountry,
    extract: false,
  });
  if (!parsed || !parsed.isValid()) return null;

  return {
    countryCode: parsed.country ?? defaultCountry,
    internationalNumber: parsed.number,
    nationalNumber: parsed.nationalNumber,
  };
}

type PhoneFieldProps = {
  country: CountryCode;
  idPrefix: string;
  label: string;
  locale: string;
  number: string;
  onCountryChange: (country: CountryCode) => void;
  onNumberChange: (number: string) => void;
};

export function PhoneField({
  country,
  idPrefix,
  label,
  locale,
  number,
  onCountryChange,
  onNumberChange,
}: PhoneFieldProps) {
  const countries = useMemo(() => {
    const names = new Intl.DisplayNames([locale], { type: "region" });
    return getCountries()
      .map((code) => ({
        code,
        dialCode: getCountryCallingCode(code),
        name: names.of(code) ?? code,
      }))
      .sort((left, right) => {
        const leftIsAfrican = africanCountries.has(left.code);
        const rightIsAfrican = africanCountries.has(right.code);
        if (leftIsAfrican !== rightIsAfrican) return leftIsAfrican ? -1 : 1;
        return left.name.localeCompare(right.name, locale);
      });
  }, [locale]);

  return (
    <div className="account-phone-fields">
      <div>
        <label htmlFor={`${idPrefix}-country`}>Pays et indicatif</label>
        <select
          id={`${idPrefix}-country`}
          autoComplete="country"
          value={country}
          onChange={(event) => {
            const selectedCountry = event.currentTarget.value;
            if (supportedCountries.has(selectedCountry)) {
              onCountryChange(selectedCountry as CountryCode);
            }
          }}
        >
          {countries.map((option) => (
            <option key={option.code} value={option.code}>
              {option.name} (+{option.dialCode})
            </option>
          ))}
        </select>
      </div>
      <div>
        <label htmlFor={`${idPrefix}-number`}>{label}</label>
        <input
          id={`${idPrefix}-number`}
          type="tel"
          autoComplete="tel"
          inputMode="tel"
          required
          value={number}
          onChange={(event) => onNumberChange(event.target.value)}
        />
      </div>
    </div>
  );
}
